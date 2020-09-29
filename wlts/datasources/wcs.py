#
# This file is part of Web Land Trajectory Service.
# Copyright (C) 2019 INPE.
#
# Web Land Trajectory Service is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""WLTS WCS DataSource."""
import urllib.request
from uuid import uuid4
from xml.dom import minidom

import base64
import gdal
import requests
from osgeo import osr
from shapely.geometry import Point
from werkzeug.exceptions import NotFound
from functools import lru_cache

from wlts.datasources.datasource import DataSource
from wlts.utils import get_date_from_str

class WCS:
    """WCS Utility Class."""

    def __init__(self, host, **kwargs):
        """Create a WFS client attached to the given host address (an URL)."""
        invalid_parameters = set(kwargs) - {"auth"}

        if invalid_parameters:
            raise AttributeError('invalid parameter(s): {}'.format(invalid_parameters))

        self.host = host
        self.base_path = "wcs?service=WCS&version=1.0.0"

        self._auth = None

        if 'auth' in kwargs:
            if kwargs['auth'] is not None:
                if not type(kwargs['auth']) is tuple:
                    raise AttributeError('auth must be a tuple ("user", "pass")')
                if len(kwargs['auth']) != 2:
                    raise AttributeError('auth must be a tuple with 2 values ("user", "pass")')
                self._auth = kwargs['auth']

    def _get_image(self, uri):
        """Get Response."""
        if self._auth:
            request = urllib.request.Request(uri)

            credentials = ('%s:%s' % (self._auth[0], self._auth[1])).replace('\n', '')
            encoded_credentials = base64.b64encode(credentials.encode('ascii'))

            request.add_header('Accept-Encoding', "gzip")
            request.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

        else:
            request = urllib.request.Request(uri, headers={"Accept-Encoding": "gzip"})

        try:
            response = urllib.request.urlopen(request, timeout=30)
            if response.info().get('Content-Encoding') == 'gzip':
               return None
            else:
                return response
        except urllib.request.URLError:
            return None

    def _get(self, uri):
        """Get URI."""
        response = requests.get(uri, auth=self._auth)

        if (response.status_code) != 200:
            raise Exception("Request Fail: {} ".format(response.status_code))

        return response.content.decode('utf-8')


    def list_image(self):
        """List collection."""
        url = "{}/{}&request=GetCapabilities&outputFormat=application/json".format(self.host, self.base_path)

        doc = self._get(url)

        xmldoc = minidom.parseString(doc)

        itemlist = xmldoc.getElementsByTagName('wcs:ContentMetadata')

        avaliables = []

        for s in itemlist[0].childNodes:
            avaliables.append(s.childNodes[0].firstChild.nodeValue)

        return avaliables

    def check_image(self, ft_name):
        """Utility to check image existence in wcs."""
        images = self.list_image()

        if ft_name not in images:
            raise NotFound('Image "{}" not found'.format(ft_name))


    def transform_latlong_to_rowcol(self, data_set, lat, long):
        """Transform the pixel location of a geospatial coordinate."""
        srs = osr.SpatialReference()
        srs.ImportFromWkt(data_set.GetProjection())

        srs_lat_long = srs.CloneGeogCS()
        ct = osr.CoordinateTransformation(srs_lat_long, srs)
        x, y, _ = ct.TransformPoint(long, lat)

        transform = data_set.GetGeoTransform()

        x = int((x - transform[0]) / transform[1])
        y = int((transform[3] - y) / -transform[5])

        return x, y

    def open_image(self, url, long, lat):
        """Open Image."""
        image_data = self._get_image(url)

        if not image_data:
            return None

        mmap_name = "/vsimem/" + uuid4().hex

        gdal.FileFromMemBuffer(mmap_name, image_data.read())
        gdal_dataset = gdal.Open(mmap_name)

        if gdal_dataset is not None:
            x, y = self.transform_latlong_to_rowcol(gdal_dataset, lat, long)

            intval = gdal_dataset.GetRasterBand(1).ReadAsArray(x, y, 1, 1).astype("int")

            gdal_dataset = None
            # Free memory associated with the in-memory file
            gdal.Unlink(mmap_name)

            if intval is not None:
                return intval[0][0]
            else:
                return intval

        else:
            return None

    @lru_cache()
    def get_image(self, image, srid, min_x, max_x, min_y, max_y, column, row, time, x, y):
        """Get Image."""
        url = "{}/{}&request=GetCoverage&COVERAGE={}&".format(self.host, self.base_path, image)

        url += "CRS=EPSG:4326&RESPONSE_CRS=EPSG:{}&".format(srid)

        url += "BBOX={},{},{},{}".format(min_x, max_x, min_y, max_y)

        url += "&FORMAT=GeoTIFF&WIDTH={}&HEIGHT={}&time={}".format(column, row, time)

        featureID = self.open_image(url, x, y)

        return featureID


class WCSDataSource(DataSource):
    """WCSDataSource Class."""

    def __init__(self, id, ds_info):
        """WCS Init Method."""
        super().__init__(id)

        if 'user' in ds_info and 'password' in ds_info:
            self._wcs = WCS(ds_info['host'], auth=(ds_info["user"], ds_info["password"]))
        else:
            self._wcs = WCS(ds_info['host'])

        self.workspace = ds_info['workspace']

    def get_type(self):
        """Get DataSource type."""
        return "WCS"

    def get_trajectory(self, **kwargs):
        """Return trajectory for wcs."""
        invalid_parameters = set(kwargs) - {"image", "temporal",
                                            "x", "y", "srid",
                                            "grid", "start_date", "end_date", "time"}
        if invalid_parameters:
            raise AttributeError('invalid parameter(s): {}'.format(invalid_parameters))

        ts = get_date_from_str(kwargs['time'])
        if kwargs['start_date']:
            start_date = get_date_from_str(kwargs['start_date'])
            if  ts < start_date:
                return None
        if kwargs['end_date']:
            end_date = get_date_from_str(kwargs['end_date'])
            if ts > end_date:
                return None

        image_name = self.workspace + ":" + kwargs['image']

        # verifica se a image existe no geoserver
        # self._wcs.check_image(image_name)

        min_x, min_y, max_x, max_y = Point(kwargs['x'], kwargs['y']).buffer(0.002).bounds

        imageID = self._wcs.get_image(image_name, kwargs['srid'],
                                            min_x , min_y, max_x, max_y,
                                            (kwargs['grid'])['column'], (kwargs['grid'])['row'],
                                            kwargs['time'], kwargs['x'], kwargs['y'])

        return imageID