# -*- coding: utf-8 -*-
"""
SVG Processing Module for Inkscape2Symbol
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from qgis.PyQt.QtGui import QColor

from .symbol_style import SymbolStyle

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
        """Validate that file is a supported SVG."""
        if not file_path.exists():
            return False, "File does not exist"

        if not file_path.suffix.lower() == '.svg':
            return False, "File is not an SVG (wrong extension)"

        if file_path.stat().st_size == 0:
            return False, "File is empty"

        if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB limit
            return False, "File is too large (>10MB)"

        try:
            ET.parse(str(file_path))
        except ET.ParseError as e:
            return False, f"Invalid XML: {str(e)}"

        return True, None

    @staticmethod
    def is_inkscape_svg(root: ET.Element) -> bool:
        """Check if SVG appears to be from Inkscape."""
        root_str = ET.tostring(root, encoding='unicode')
        return 'inkscape' in root_str or 'sodipodi' in root_str


@dataclass
class SVGDimensions:
    """Container for SVG dimensions."""
    width: str
    height: str
    viewBox: str

    def __str__(self) -> str:
        return f"{self.width}×{self.height} (viewBox: {self.viewBox})"


class SVGProcessor:
    """Processes SVG files to create QGIS-compatible symbols."""

    def __init__(self):
        """Initialize the SVG processor."""
        self._tree: Optional[ET.ElementTree] = None
        self._root: Optional[ET.Element] = None
        self._original_style: Optional[SymbolStyle] = None
        self._dimensions: Optional[SVGDimensions] = None
        self._processed_svg: Optional[str] = None
        self._preview_svg: Optional[str] = None
        self._file_path: Optional[Path] = None

    def load_svg(self, file_path: Path) -> None:
        """Load and validate an SVG file."""
        logger.info(f"Loading SVG: {file_path}")

        # Validate file
        is_valid, error = SVGValidator.validate_file(file_path)
        if not is_valid:
            raise SVGProcessingError(error)

        try:
            self._tree = ET.parse(str(file_path))
            self._root = self._tree.getroot()
            self._file_path = file_path

            if not SVGValidator.is_inkscape_svg(self._root):
                logger.warning("SVG may not be from Inkscape")

            self._dimensions = self._extract_dimensions()
            logger.info(f"SVG dimensions: {self._dimensions}")

            self._original_style = self._extract_original_style()
            logger.info(f"Original style: fill={self._original_style.fill_color.name()}, "
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

        # Clean up units
        for unit in ['px', 'mm', 'pt', 'cm', 'in']:
            width = width.replace(unit, '')
            height = height.replace(unit, '')

        return SVGDimensions(width=width, height=height, viewBox=viewBox)

    def _extract_original_style(self) -> SymbolStyle:
        """Extract original fill and stroke colors from SVG."""
        fill_color = QColor('#DCDCDC')
        outline_color = QColor('#000000')

        shape_tags = ['path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line']

        # Try to find any shape element, handling namespaces
        for elem in self._root.iter():
            # Handle both namespaced (e.g. {http://...}path or svg:path) and non-namespaced tags
            tag_name = elem.tag
            if '}' in tag_name:
                # Namespaced like {http://www.w3.org/2000/svg}path
                tag_name = tag_name.split('}')[-1]
            elif ':' in tag_name:
                # Prefix notation like svg:path
                tag_name = tag_name.split(':')[-1]

            logger.debug(f"Checking element: {elem.tag} -> normalized: {tag_name}")

            if tag_name not in shape_tags:
                continue

            logger.debug(f"  Found shape: {tag_name}")
            logger.debug(f"  Attributes: {dict(elem.attrib)}")

            # Check style attribute first
            style = elem.get('style', '')
            if style:
                logger.debug(f"  style attribute: {style}")
                fill = self._extract_color_from_style(style, 'fill')
                stroke = self._extract_color_from_style(style, 'stroke')

                logger.debug(f"  extracted from style - fill: {fill}, stroke: {stroke}")

                if fill and fill != 'none':
                    color = self._extract_color_from_param(fill)
                    logger.debug(f"  parsed fill color: {color}")
                    if color:
                        fill_color = QColor(color)

                if stroke and stroke != 'none':
                    color = self._extract_color_from_param(stroke)
                    logger.debug(f"  parsed stroke color: {color}")
                    if color:
                        outline_color = QColor(color)

                if fill or stroke:
                    break

            # Check direct attributes
            fill_attr = elem.get('fill')
            stroke_attr = elem.get('stroke')

            # Use print to bypass logger issues
            print(f"[DEBUG] fill attribute RAW: '{fill_attr}'")
            print(f"[DEBUG] stroke attribute RAW: '{stroke_attr}'")

            if fill_attr and fill_attr != 'none':
                color = self._extract_color_from_param(fill_attr)
                print(f"[DEBUG] parsed fill from attribute: '{color}'")
                if color:
                    fill_color = QColor(color)
                    print(f"[DEBUG] QColor fill: {fill_color.name()}")

            if stroke_attr and stroke_attr != 'none':
                color = self._extract_color_from_param(stroke_attr)
                print(f"[DEBUG] parsed stroke from attribute: '{color}'")
                if color:
                    outline_color = QColor(color)
                    print(f"[DEBUG] QColor stroke: {outline_color.name()}")

            if fill_attr or stroke_attr:
                print(f"[DEBUG] Found colors - breaking. Fill: {fill_color.name()}, Stroke: {outline_color.name()}")
                break

        logger.info(f"Final extracted colors - fill: {fill_color.name()}, outline: {outline_color.name()}")

        return SymbolStyle(
            fill_color=fill_color,
            outline_color=outline_color,
            outline_width=0.2,
            has_outline=True
        )

    @staticmethod
    def _extract_color_from_style(style: str, property_name: str) -> Optional[str]:
        """Extract a color value from a style string."""
        if not style:
            return None

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

    @staticmethod
    def _extract_color_from_param(value: str) -> Optional[str]:
        """
        Extract color from either regular format or param() format.

        Examples:
            "#fff176" -> "#fff176"
            "param(fill) #fff176" -> "#fff176"
            "param(outline) rgb(255,127,0)" -> "rgb(255,127,0)"
        """
        if not value or value == 'none':
            return None

        # If it starts with param(), extract the default color after it
        if value.startswith('param('):
            # Format: "param(name) #color" or "param(name) rgb(...)"
            parts = value.split(')', 1)
            if len(parts) == 2:
                color = parts[1].strip()
                if color and color != 'none':
                    return color
            return None

        # Regular color value
        return value

    def process(self, style: SymbolStyle) -> str:
        """
        Process the SVG with the given style parameters.

        Creates TWO versions:
        1. Preview version (regular SVG for display in Qt)
        2. Export version (QGIS parametric SVG for saving)

        Returns the EXPORT version (with param() syntax).
        """
        if self._root is None:
            raise SVGProcessingError("No SVG loaded")

        logger.info(f"Processing SVG with style: {style.to_dict()}")

        try:
            import copy

            # Create PREVIEW version (regular SVG)
            preview_root = copy.deepcopy(self._root)
            self._clean_root_attributes(preview_root)
            self._apply_regular_style_recursive(preview_root, style)
            self._preview_svg = self._to_string(preview_root)

            # Create EXPORT version (QGIS parametric)
            export_root = copy.deepcopy(self._root)
            self._clean_root_attributes(export_root)
            export_root.set('i2s', 'yes')
            self._apply_qgis_parameters_recursive(export_root, style)
            self._processed_svg = self._to_string(export_root)

            logger.info("SVG processing complete")
            return self._processed_svg

        except Exception as e:
            logger.exception("Processing failed")
            raise SVGProcessingError(f"Processing failed: {str(e)}")

    def _clean_root_attributes(self, root: ET.Element) -> None:
        """Remove Inkscape/Sodipodi attributes from root element."""
        attrs_to_remove = []
        for key in root.attrib.keys():
            if 'inkscape' in key or 'sodipodi' in key:
                attrs_to_remove.append(key)

        for key in attrs_to_remove:
            del root.attrib[key]

    def _apply_regular_style_recursive(self, elem: ET.Element, style: SymbolStyle) -> None:
        """Apply regular (non-parametric) styling for preview."""
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        shape_tags = ['path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line']

        if tag_name in shape_tags:
            self._apply_regular_style_to_element(elem, style)

        # Process children
        for child in elem:
            self._apply_regular_style_recursive(child, style)

    def _apply_regular_style_to_element(self, elem: ET.Element, style: SymbolStyle) -> None:
        """Apply regular SVG styling (for preview in QSvgWidget)."""
        outline_width = '0.0' if not style.has_outline else str(style.outline_width)
        fill_hex = style.fill_color.name()
        stroke_hex = style.outline_color.name()

        # Remove old style attribute
        if 'style' in elem.attrib:
            del elem.attrib['style']

        # Set regular SVG attributes (Qt can render these)
        elem.set('fill', fill_hex)
        elem.set('stroke', stroke_hex)
        elem.set('stroke-width', outline_width)
        elem.set('fill-opacity', '1')
        elem.set('stroke-opacity', '1')

    def _apply_qgis_parameters_recursive(self, elem: ET.Element, style: SymbolStyle) -> None:
        """Apply QGIS parametric styling for export."""
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        shape_tags = ['path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line']

        if tag_name in shape_tags:
            self._apply_qgis_style_to_element(elem, style)

        # Process children
        for child in elem:
            self._apply_qgis_parameters_recursive(child, style)

    def _apply_qgis_style_to_element(self, elem: ET.Element, style: SymbolStyle) -> None:
        """Apply QGIS parametric style (for saving)."""
        outline_width = '0.0' if not style.has_outline else str(style.outline_width)
        fill_hex = style.fill_color.name()
        stroke_hex = style.outline_color.name()

        # Remove old style attribute
        if 'style' in elem.attrib:
            del elem.attrib['style']

        # Set QGIS parametric attributes
        elem.set('fill', f'param(fill) {fill_hex}')
        elem.set('stroke', f'param(outline) {stroke_hex}')
        elem.set('stroke-width', f'param(outline-width) {outline_width}')
        elem.set('fill-opacity', '1')
        elem.set('stroke-opacity', '1')

    def _to_string(self, root: ET.Element) -> str:
        """Convert element tree to SVG string."""
        xml_string = ET.tostring(root, encoding='unicode', method='xml')

        if not xml_string.startswith('<?xml'):
            xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string

        return xml_string

    def get_original_style(self) -> Optional[SymbolStyle]:
        """Get the original style extracted from the SVG."""
        return self._original_style

    def get_processed_svg(self) -> str:
        """
        Get the EXPORT version (with QGIS param() syntax).
        This is what gets saved to file.
        """
        if not self._processed_svg:
            raise SVGProcessingError("No SVG has been processed yet")
        return self._processed_svg

    def get_preview_svg(self) -> str:
        """
        Get the PREVIEW version (regular SVG for display).
        This is what gets shown in QSvgWidget.
        """
        if not self._preview_svg:
            raise SVGProcessingError("No SVG has been processed yet")
        return self._preview_svg

    def is_loaded(self) -> bool:
        """Check if an SVG is currently loaded."""
        return self._root is not None

    def get_dimensions(self) -> Optional[SVGDimensions]:
        """Get SVG dimensions."""
        return self._dimensions

    def get_file_path(self) -> Optional[Path]:
        """Get the path of the loaded file."""
        return self._file_path
