# -*- coding: utf-8 -*-
from __future__ import annotations

"""
SVG Processing Module for Inkscape2Symbol

Handles SVG file parsing, validation, and conversion to QGIS-compatible format.
Uses proper XML parsing instead of string manipulation.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from io import StringIO

from qgis.PyQt.QtGui import QColor

logger = logging.getLogger(__name__)

# SVG namespaces
NS = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
    'xlink': 'http://www.w3.org/1999/xlink'
}

# Register namespaces for output
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


class SVGProcessingError(Exception):
    """Raised when SVG processing fails."""
    pass


class SVGValidator:
    """Validates SVG files for compatibility."""

    @staticmethod
    def validate_file(file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate that file is a supported SVG.

        Args:
            file_path: Path to SVG file

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file_path.exists():
            return False, "File does not exist"

        if not file_path.suffix.lower() == '.svg':
            return False, "File is not an SVG (wrong extension)"

        if file_path.stat().st_size == 0:
            return False, "File is empty"

        if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB limit
            return False, "File is too large (>10MB)"

        try:
            # Try to parse as XML
            ET.parse(str(file_path))
        except ET.ParseError as e:
            return False, f"Invalid XML: {str(e)}"

        return True, None

    @staticmethod
    def is_inkscape_svg(root: ET.Element) -> bool:
        """Check if SVG appears to be from Inkscape."""
        # Check for Inkscape namespace
        if any(attr.startswith('{' + NS['inkscape']) for attr in root.attrib.keys()):
            return True

        # Check for Inkscape elements
        if root.find('.//{' + NS['inkscape'] + '}*') is not None:
            return True

        return False


@dataclass
class SVGDimensions:
    """Container for SVG dimensions."""
    width: str
    height: str
    viewBox: str

    def __str__(self) -> str:
        return f"{self.width}×{self.height} (viewBox: {self.viewBox})"


class SVGProcessor:
    """
    Processes SVG files to create QGIS-compatible symbols.

    This class handles:
    - Loading and validating SVG files
    - Extracting original styling
    - Converting to QGIS parameter format
    - Removing Inkscape-specific elements
    """

    def __init__(self):
        """Initialize the SVG processor."""
        self._tree: Optional[ET.ElementTree] = None
        self._root: Optional[ET.Element] = None
        self._original_style: Optional[SymbolStyle] = None
        self._dimensions: Optional[SVGDimensions] = None
        self._processed_svg: Optional[str] = None
        self._file_path: Optional[Path] = None

    def load_svg(self, file_path: Path) -> None:
        """
        Load and validate an SVG file.

        Args:
            file_path: Path to the SVG file

        Raises:
            SVGProcessingError: If file is invalid or can't be loaded
        """
        logger.info(f"Loading SVG: {file_path}")

        # Validate file
        is_valid, error = SVGValidator.validate_file(file_path)
        if not is_valid:
            raise SVGProcessingError(error)

        try:
            # Parse XML
            self._tree = ET.parse(str(file_path))
            self._root = self._tree.getroot()
            self._file_path = file_path

            # Check if it's an Inkscape SVG
            if not SVGValidator.is_inkscape_svg(self._root):
                logger.warning("SVG may not be from Inkscape")

            # Extract dimensions
            self._dimensions = self._extract_dimensions()
            logger.info(f"SVG dimensions: {self._dimensions}")

            # Extract original style
            self._original_style = self._extract_original_style()
            logger.info(f"Original style extracted: fill={self._original_style.fill_color.name()}, "
                        f"outline={self._original_style.outline_color.name()}")

        except ET.ParseError as e:
            raise SVGProcessingError(f"Failed to parse SVG: {str(e)}")
        except Exception as e:
            raise SVGProcessingError(f"Error loading SVG: {str(e)}")

    def _extract_dimensions(self) -> SVGDimensions:
        """Extract width, height, and viewBox from SVG root."""
        width = self._root.get('width', '100')
        height = self._root.get('height', '100')
        viewBox = self._root.get('viewBox', f'0 0 {width} {height}')

        return SVGDimensions(width=width, height=height, viewBox=viewBox)

    def _extract_original_style(self) -> SymbolStyle:
        """
        Extract original fill and stroke colors from SVG.

        Returns:
            SymbolStyle with original colors
        """
        # Import here to avoid circular import
        from .inkscape2symbol_improved import SymbolStyle

        # Default colors
        fill_color = QColor('#DCDCDC')
        outline_color = QColor('#000000')

        # Look for style in various places
        # 1. Check style attributes in paths/shapes
        for elem in self._root.iter():
            if elem.tag.endswith('path') or elem.tag.endswith('rect') or \
                    elem.tag.endswith('circle') or elem.tag.endswith('ellipse'):

                # Check style attribute
                style = elem.get('style', '')
                fill = self._extract_color_from_style(style, 'fill')
                stroke = self._extract_color_from_style(style, 'stroke')

                if fill:
                    fill_color = QColor(fill)
                if stroke:
                    outline_color = QColor(stroke)

                # Check direct attributes
                if not fill and elem.get('fill'):
                    fill_color = QColor(elem.get('fill'))
                if not stroke and elem.get('stroke'):
                    outline_color = QColor(elem.get('stroke'))

                # If we found both, we're done
                if fill and stroke:
                    break

        return SymbolStyle(
            fill_color=fill_color,
            outline_color=outline_color,
            outline_width=0.2,
            has_outline=True
        )

    @staticmethod
    def _extract_color_from_style(style: str, property_name: str) -> Optional[str]:
        """
        Extract a color value from a style string.

        Args:
            style: CSS style string (e.g., "fill:#ff0000;stroke:#000000")
            property_name: Property to extract (e.g., "fill" or "stroke")

        Returns:
            Color value or None if not found
        """
        if not style:
            return None

        # Parse CSS-style properties
        for prop in style.split(';'):
            prop = prop.strip()
            if ':' not in prop:
                continue

            key, value = prop.split(':', 1)
            key = key.strip()
            value = value.strip()

            if key == property_name and value and value != 'none':
                return value

        return None

    def process(self, style: SymbolStyle) -> str:
        """
        Process the SVG with the given style parameters.

        Args:
            style: Style parameters to apply

        Returns:
            Processed SVG as string

        Raises:
            SVGProcessingError: If processing fails
        """
        if not self._root:
            raise SVGProcessingError("No SVG loaded")

        logger.info(f"Processing SVG with style: {style.to_dict()}")

        try:
            # Create a working copy
            root_copy = self._create_clean_copy()

            # Apply QGIS parameter format
            self._apply_qgis_parameters(root_copy, style)

            # Convert to string
            self._processed_svg = self._to_string(root_copy)

            logger.info("SVG processing complete")
            return self._processed_svg

        except Exception as e:
            raise SVGProcessingError(f"Processing failed: {str(e)}")

    def _create_clean_copy(self) -> ET.Element:
        """
        Create a clean copy of SVG root, removing Inkscape-specific elements.

        Returns:
            Cleaned SVG root element
        """
        # Create new root with essential attributes
        svg_attribs = {
            'width': self._dimensions.width,
            'height': self._dimensions.height,
            'viewBox': self._dimensions.viewBox,
            'xmlns': NS['svg'],
            'enable-background': f'new {self._dimensions.viewBox}',
            'i2s': 'yes'  # Mark as processed by Inkscape2Symbol
        }

        new_root = ET.Element(f'{{{NS["svg"]}}}svg', attrib=svg_attribs)

        # Copy content, filtering out Inkscape/Sodipodi elements
        for elem in self._root:
            if self._should_include_element(elem):
                new_root.append(self._clean_element(elem))

        return new_root

    def _should_include_element(self, elem: ET.Element) -> bool:
        """Check if element should be included in output."""
        tag = elem.tag

        # Exclude Inkscape/Sodipodi metadata
        if tag.startswith('{' + NS['inkscape']) or \
                tag.startswith('{' + NS['sodipodi']):
            return False

        # Exclude defs if empty or only metadata
        if tag.endswith('defs'):
            # Check if it has useful content
            has_content = any(
                not (child.tag.startswith('{' + NS['inkscape']) or
                     child.tag.startswith('{' + NS['sodipodi']))
                for child in elem
            )
            return has_content

        # Exclude metadata
        if tag.endswith('metadata'):
            return False

        return True

    def _clean_element(self, elem: ET.Element) -> ET.Element:
        """
        Recursively clean an element and its children.

        Args:
            elem: Element to clean

        Returns:
            Cleaned element
        """
        # Create new element without namespace attributes
        new_attribs = {}
        for key, value in elem.attrib.items():
            # Skip Inkscape/Sodipodi attributes
            if key.startswith('{' + NS['inkscape']) or \
                    key.startswith('{' + NS['sodipodi']):
                continue
            new_attribs[key] = value

        new_elem = ET.Element(elem.tag, attrib=new_attribs)
        new_elem.text = elem.text
        new_elem.tail = elem.tail

        # Recursively clean children
        for child in elem:
            if self._should_include_element(child):
                new_elem.append(self._clean_element(child))

        return new_elem

    def _apply_qgis_parameters(self, root: ET.Element, style: SymbolStyle) -> None:
        """
        Apply QGIS parametric styling to SVG elements.

        Args:
            root: SVG root element
            style: Style to apply
        """
        # Find all shape elements
        shape_tags = ['path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line']

        for tag in shape_tags:
            for elem in root.iter(f'{{{NS["svg"]}}}{tag}'):
                self._apply_style_to_element(elem, style)

    def _apply_style_to_element(self, elem: ET.Element, style: SymbolStyle) -> None:
        """
        Apply QGIS parametric style to a single element.

        Args:
            elem: Element to style
            style: Style to apply
        """
        outline_width = '0.0' if not style.has_outline else str(style.outline_width)

        # Build CSS style string
        css_style = (
            f'opacity:1;'
            f'fill:{style.fill_color.name()};'
            f'fill-opacity:1;'
            f'stroke:{style.outline_color.name()};'
            f'stroke-width:{outline_width};'
            f'stroke-opacity:1'
        )

        # Set style attribute
        elem.set('style', css_style)

        # Add QGIS parameter attributes
        elem.set('fill', f'param(fill) {style.fill_color.name()}')
        elem.set('stroke', f'param(outline) {style.outline_color.name()}')
        elem.set('stroke-width', f'param(outline-width) {outline_width}')

    def _to_string(self, root: ET.Element) -> str:
        """
        Convert element tree to SVG string.

        Args:
            root: SVG root element

        Returns:
            SVG as string
        """
        # Convert to bytes first
        xml_bytes = ET.tostring(root, encoding='unicode', method='xml')

        # Add XML declaration
        svg_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes

        return svg_string

    def get_original_style(self) -> Optional[SymbolStyle]:
        """Get the original style extracted from the SVG."""
        return self._original_style

    def get_processed_svg(self) -> str:
        """
        Get the last processed SVG.

        Returns:
            Processed SVG string

        Raises:
            SVGProcessingError: If no SVG has been processed
        """
        if not self._processed_svg:
            raise SVGProcessingError("No SVG has been processed yet")
        return self._processed_svg

    def is_loaded(self) -> bool:
        """Check if an SVG is currently loaded."""
        return self._root is not None

    def get_dimensions(self) -> Optional[SVGDimensions]:
        """Get SVG dimensions."""
        return self._dimensions

    def get_file_path(self) -> Optional[Path]:
        """Get the path of the loaded file."""
        return self._file_path


# Import SymbolStyle from main module
from .inkscape2symbol_improved import SymbolStyle