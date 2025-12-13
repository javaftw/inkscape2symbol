# -*- coding: utf-8 -*-
"""
Symbol Style Data Classes for Inkscape2Symbol
"""

from dataclasses import dataclass
from typing import Dict, Any
from qgis.PyQt.QtGui import QColor


@dataclass
class SymbolStyle:
    """Container for symbol style parameters."""
    fill_color: QColor
    outline_color: QColor
    outline_width: float = 0.2
    has_outline: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert style to dictionary for serialization."""
        return {
            'fill': self.fill_color.name(),
            'outline': self.outline_color.name(),
            'outline_width': self.outline_width,
            'has_outline': self.has_outline
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SymbolStyle':
        """Create style from dictionary."""
        return cls(
            fill_color=QColor(data['fill']),
            outline_color=QColor(data['outline']),
            outline_width=data.get('outline_width', 0.2),
            has_outline=data.get('has_outline', True)
        )