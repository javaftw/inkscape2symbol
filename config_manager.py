# -*- coding: utf-8 -*-
"""
Configuration Management Module for Inkscape2Symbol

Handles loading, saving, and managing user preferences and settings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QColor

from .symbol_style import SymbolStyle

logger = logging.getLogger(__name__)


@dataclass
class ColorPreset:
    """A saved color preset."""
    name: str
    fill_color: str
    outline_color: str
    has_outline: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ColorPreset:
        """Create from dictionary."""
        return cls(**data)


class ConfigManager:
    """
    Manages plugin configuration and user preferences.

    Settings are stored in QSettings (platform-appropriate location)
    Additional data like presets are stored in JSON files.
    """

    # Default settings
    DEFAULTS = {
        'default_fill_color': '#DCDCDC',
        'default_outline_color': '#000000',
        'default_outline_width': 0.2,
        'default_has_outline': True,
        'default_output_dir': '',
        'log_level': 'INFO',
        'auto_preview': True,
        'show_tooltips': True,
        'recent_files_max': 10,
        'window_geometry': None,
    }

    # Built-in color presets
    BUILTIN_PRESETS = [
        ColorPreset('Default Gray', '#DCDCDC', '#000000'),
        ColorPreset('Red', '#FF6B6B', '#8B0000'),
        ColorPreset('Blue', '#4ECDC4', '#003366'),
        ColorPreset('Green', '#95E1D3', '#2F5233'),
        ColorPreset('Orange', '#FFB347', '#CC5500'),
        ColorPreset('Purple', '#C19CF0', '#4B0082'),
        ColorPreset('Yellow', '#FFF176', '#FF8F00'),
        ColorPreset('Teal', '#80CBC4', '#004D40'),
        ColorPreset('Pink', '#F48FB1', '#880E4F'),
        ColorPreset('Brown', '#BCAAA4', '#3E2723'),
        ColorPreset('No Outline', '#DCDCDC', '#000000', False),
    ]

    def __init__(self, plugin_dir: Path):
        """
        Initialize configuration manager.

        Args:
            plugin_dir: Path to plugin directory
        """
        self.plugin_dir = plugin_dir
        self.config_dir = plugin_dir / 'config'
        self.config_dir.mkdir(exist_ok=True)

        # QSettings for persistent storage
        self.settings = QSettings('Anthropic', 'Inkscape2Symbol')

        # Paths to data files
        self.presets_file = self.config_dir / 'color_presets.json'
        self.recent_files_file = self.config_dir / 'recent_files.json'

        # Cache
        self._custom_presets: Optional[List[ColorPreset]] = None
        self._recent_files: Optional[List[str]] = None

        logger.info(f"ConfigManager initialized with dir: {self.config_dir}")

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        # Use provided default or class default
        if default is None:
            default = self.DEFAULTS.get(key)

        value = self.settings.value(key, default)
        logger.debug(f"Get setting: {key} = {value}")
        return value

    def set_setting(self, key: str, value: Any) -> None:
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Value to set
        """
        self.settings.setValue(key, value)
        self.settings.sync()
        logger.debug(f"Set setting: {key} = {value}")

    def get_all_presets(self) -> List[ColorPreset]:
        """
        Get all color presets (built-in + custom).

        Returns:
            List of all presets
        """
        custom_presets = self.get_custom_presets()
        return self.BUILTIN_PRESETS + custom_presets

    def get_custom_presets(self) -> List[ColorPreset]:
        """
        Get user-created color presets.

        Returns:
            List of custom presets
        """
        if self._custom_presets is not None:
            return self._custom_presets

        if not self.presets_file.exists():
            self._custom_presets = []
            return self._custom_presets

        try:
            with open(self.presets_file, 'r') as f:
                data = json.load(f)

            self._custom_presets = [
                ColorPreset.from_dict(preset)
                for preset in data.get('presets', [])
            ]
            logger.info(f"Loaded {len(self._custom_presets)} custom presets")

        except Exception as e:
            logger.error(f"Error loading presets: {e}")
            self._custom_presets = []

        return self._custom_presets

    def save_custom_presets(self, presets: List[ColorPreset]) -> None:
        """
        Save custom color presets.

        Args:
            presets: List of presets to save
        """
        try:
            data = {
                'version': '1.0',
                'presets': [preset.to_dict() for preset in presets]
            }

            with open(self.presets_file, 'w') as f:
                json.dump(data, f, indent=2)

            self._custom_presets = presets
            logger.info(f"Saved {len(presets)} custom presets")

        except Exception as e:
            logger.error(f"Error saving presets: {e}")

    def add_preset(self, preset: ColorPreset) -> None:
        """
        Add a new custom preset.

        Args:
            preset: Preset to add
        """
        presets = self.get_custom_presets()

        # Check for duplicate names
        existing_names = [p.name for p in presets]
        if preset.name in existing_names:
            # Make unique
            counter = 1
            base_name = preset.name
            while f"{base_name} ({counter})" in existing_names:
                counter += 1
            preset.name = f"{base_name} ({counter})"

        presets.append(preset)
        self.save_custom_presets(presets)

    def remove_preset(self, preset_name: str) -> bool:
        """
        Remove a custom preset by name.

        Args:
            preset_name: Name of preset to remove

        Returns:
            True if removed, False if not found
        """
        presets = self.get_custom_presets()
        original_count = len(presets)

        presets = [p for p in presets if p.name != preset_name]

        if len(presets) < original_count:
            self.save_custom_presets(presets)
            return True

        return False

    def get_recent_files(self) -> List[str]:
        """
        Get list of recently used files.

        Returns:
            List of file paths (most recent first)
        """
        if self._recent_files is not None:
            return self._recent_files

        if not self.recent_files_file.exists():
            self._recent_files = []
            return self._recent_files

        try:
            with open(self.recent_files_file, 'r') as f:
                data = json.load(f)

            self._recent_files = data.get('files', [])
            logger.info(f"Loaded {len(self._recent_files)} recent files")

        except Exception as e:
            logger.error(f"Error loading recent files: {e}")
            self._recent_files = []

        return self._recent_files

    def add_recent_file(self, file_path: str) -> None:
        """
        Add a file to the recent files list.

        Args:
            file_path: Path to add
        """
        recent = self.get_recent_files()

        # Remove if already in list
        if file_path in recent:
            recent.remove(file_path)

        # Add to front
        recent.insert(0, file_path)

        # Limit size
        max_files = self.get_setting('recent_files_max', 10)
        recent = recent[:max_files]

        # Save
        try:
            data = {
                'version': '1.0',
                'files': recent
            }

            with open(self.recent_files_file, 'w') as f:
                json.dump(data, f, indent=2)

            self._recent_files = recent
            logger.debug(f"Added recent file: {file_path}")

        except Exception as e:
            logger.error(f"Error saving recent files: {e}")

    def clear_recent_files(self) -> None:
        """Clear the recent files list."""
        self._recent_files = []
        if self.recent_files_file.exists():
            self.recent_files_file.unlink()
        logger.info("Cleared recent files")

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.settings.clear()
        self.settings.sync()

        # Clear caches
        self._custom_presets = None
        self._recent_files = None

        logger.info("Reset all settings to defaults")

    def export_settings(self, export_path: Path) -> None:
        """
        Export all settings and data to a file.

        Args:
            export_path: Path to export to
        """
        try:
            export_data = {
                'version': '1.0',
                'settings': {
                    key: self.get_setting(key)
                    for key in self.DEFAULTS.keys()
                },
                'custom_presets': [
                    preset.to_dict()
                    for preset in self.get_custom_presets()
                ],
                'recent_files': self.get_recent_files()
            }

            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported settings to: {export_path}")

        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            raise

    def import_settings(self, import_path: Path) -> None:
        """
        Import settings and data from a file.

        Args:
            import_path: Path to import from
        """
        try:
            with open(import_path, 'r') as f:
                import_data = json.load(f)

            # Import settings
            for key, value in import_data.get('settings', {}).items():
                self.set_setting(key, value)

            # Import presets
            custom_presets = [
                ColorPreset.from_dict(preset)
                for preset in import_data.get('custom_presets', [])
            ]
            self.save_custom_presets(custom_presets)

            # Import recent files
            recent_files = import_data.get('recent_files', [])
            if recent_files:
                data = {'version': '1.0', 'files': recent_files}
                with open(self.recent_files_file, 'w') as f:
                    json.dump(data, f, indent=2)
                self._recent_files = recent_files

            logger.info(f"Imported settings from: {import_path}")

        except Exception as e:
            logger.error(f"Error importing settings: {e}")
            raise