# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Inkscape2Symbol
                                 A QGIS plugin
 Import SVG drawings created in Inkscape as symbols in QGIS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2019-09-30
        copyright            : (C) 2019 by Hennie Kotze
        email                : henniek@locat.co.za
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load Inkscape2Symbol class from file Inkscape2Symbol.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .inkscape2symbol import Inkscape2Symbol
    return Inkscape2Symbol(iface)
