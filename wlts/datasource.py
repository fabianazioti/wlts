#
# This file is part of Web Land Trajectory Service.
# Copyright (C) 2019 INPE.
#
# Web Land Trajectory Service is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""WLTS data source class."""
from abc import ABCMeta, abstractmethod
from datetime import datetime
from json import loads as json_loads
from pathlib import Path
from xml.dom import minidom

import psycopg2
import requests
from shapely.geometry import Point
from werkzeug.exceptions import BadRequest, NotFound

from wlts.config import BASE_DIR

config_folder = Path(BASE_DIR) / 'json-config/'

def get_date_from_str(date, date_ref=None):
    """Utility to build date from str."""
    date = date.replace('/', '-')

    try:
        date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        try:
            date = datetime.strptime(date, '%Y-%m')
        except ValueError:
            date = datetime.strptime(date, '%Y')

    if date_ref:
        date = date.replace(day=31, month=12)

    return date

class PostgisConnection:
    """PostgisConnection.

    :param pgisInfo: Python object (dict) with connection info
    :type pgisInfo: dict

    :returns: connection.
    :rtype: psycopg2.connect

    """

    def connection_open(pgisInfo):
        """Get Connection."""
        try:
            connection = psycopg2.connect(user = pgisInfo["user"],
                                          password = pgisInfo["password"],
                                          host = pgisInfo["host"],
                                          port = pgisInfo["port"],
                                          database = pgisInfo["database"]
                                          )

            # print("Connection stabelized! ")
            return connection
        except (Exception, psycopg2.Error) as error:
            print ("Error while connecting to PostgreSQL :{}".format(error))

#TODO Pode mudar DRIVER o nome
class PostGisConnectionPool:
    """PostGisConnectionPool.

    :param pg_source: Python object (dict) with connection info
    :type pg_source: dict.

    """

    def __init__(self, pg_source):
        """Creates PostGisConnectionPool."""
        self.datasource = pg_source
        self.open_conection()

    def __del__(self):
        """Delete PostGisConnectionPool."""
        self.close_connection()

    def open_conection(self):
        """Open PostGisConnection."""
        self.pg_connection = PostgisConnection.connection_open(self.datasource.get_connection_info())

    def close_connection(self):
        """Close PostGisConnectionPool."""
        # self.pg_connection.cursor().close()
        self.pg_connection.close()

    def execute_query(self, sql):
        """Execute PostGis Query."""
        cur = self.pg_connection.cursor()
        cur.execute(sql)
        return cur.fetchall()
        # with self.pg_connection.cursor() as cursor:
        #     cursor.execute(sql)
            # for cs in cursor.fetchall():
            #     result = cs
            # cursor.close()

    def get_connection(self):
        """Get PostGisConnection."""
        return self.pg_connection

class WCSConnectionPool:
    """WCSConnectionPool.

    :param connection_info: Connection info
    :type connection_info: dict.

    """

    def __init__(self, connection_info):
        """Creates WCSConnectionPool."""
        self.host = connection_info["host"]
        self.port = connection_info["port"]
        self.location = connection_info["location"]
        self.workspace = "datacube"
        self.base_path = "wcs?service=WCS&version=1.0.0"
        self.auth = None

        if(connection_info["user"] and connection_info["password"]):
            self.auth = (connection_info["user"], connection_info["password"])

        self.base = self.mount_url()

    def mount_url(self):
        """Mount Url."""
        all_url = self.host + ":" + self.port + "/" + self.location + "/" + self.workspace

        return all_url

    def _get(self, uri):
        """Get Response."""
        response = requests.get(uri, auth=self.auth)

        if (response.status_code) != 200:
            raise Exception("Request Fail: {} ".format(response.status_code))

        return response.content.decode('utf-8')

    def list_collection(self):
        """List collection."""
        url = "{}/{}&request=GetCapabilities".format(self.base,self.base_path)

        doc = self._get(url)

        xmldoc = minidom.parseString(doc)

        xmldoc.toxml()


class WFSConnectionPool:
    """WFSConnectionPool.

    :param connection_info: Connection info
    :type connection_info: dict.

    """

    def __init__(self, connection_info):
        """Creates WFSConnectionPool."""
        self.host = connection_info["host"]
        self.port = connection_info["port"]
        self.location = connection_info["location"]
        self.workspace = "datacube"
        self.base_path = "wfs?service=WFS&version=1.0.0"
        self.auth = None

        if(connection_info["user"] and connection_info["password"]):
            self.auth = (connection_info["user"], connection_info["password"])

        self.base = self.mount_url()

    def _get(self, uri):
        """Get WFS."""
        response = requests.get(uri, auth=self.auth)

        if (response.status_code) != 200:
            raise Exception("Request Fail: {} ".format(response.status_code))

        return response.content.decode('utf-8')

    def mount_url(self):
        """Mount url WFS."""
        all_url = self.host + ":" + self.port + "/" + self.location + "/" + self.workspace

        return all_url

    def list_feature(self):
        """List Feature WFS."""
        url = "{}/{}&request=GetCapabilities".format(self.base,self.base_path)

        doc = self._get(url)

        xmldoc = minidom.parseString(doc)
        itemlist = xmldoc.getElementsByTagName('FeatureType')

        features = dict()
        features[u'features'] = []

        for s in itemlist:
            features[u'features'].append(s.childNodes[0].firstChild.nodeValue)

        return features

    def describe_feature(self, ft_name):
        """Describe Feature WFS."""
        url = "{}/{}&request=DescribeFeatureType&typeName={}".format(self.base, self.base_path, ft_name)

        doc = self._get(url)

         # TODO verificar se veio erro
        # if 'exception' in doc:
        #    raise Exception(doc["exception"])

        js = json_loads(doc)

        # print(js)

    def get_feature(self, **kwargs):
        """Retrieve the feature collection given feature.

        Keyword arguments:ft_name, geom, geom_property,propertyName, srid,  date

        :param kwargs: Keyword arguments
        """
        invalid_parameters = set(kwargs) - {'geom_property', 'feature_type', 'srid', 'geom', 'propertyName', 'start_date', 'end_date'}

        if invalid_parameters:
            raise AttributeError('invalid parameter(s): {}'.format(invalid_parameters))

        # verifica se a feature existe
        self.check_feature(kwargs['feature_type'])

        url = "{}/{}&request=GetFeature&typeName={}".format(self.base, self.base_path, kwargs['feature_type'])

        if 'propertyName' in kwargs:
            url+= "&propertyName={}".format(kwargs['propertyName'])

        url += "&outputformat=json&CRS=EPSG:{}".format(kwargs['srid'])

        url += "&CQL_FILTER=INTERSECTS({}, {})".format((kwargs['geom_property'])['property_name'], (kwargs['geom']).wkt)

        if 'start_date' in kwargs:
            url += kwargs['start_date']

        if 'end_date' in kwargs:
            url += kwargs['end_date']

        doc = self._get(url)

        # print(url)

        js = json_loads(doc)

        if(js["features"]):
            return js["features"][0]["properties"]

        return

    def get_class(self, featureID, class_property_name, ft_name, workspace = 'datacube'):
        """Get classes of given feature."""
        url = "{}/{}&request=GetFeature&typeName={}&featureID={}".format(self.base, self.base_path, ft_name, featureID)

        doc = self._get(url)

        xmldoc = minidom.parseString(doc)

        # print(xmldoc.toxml())

        tagName = workspace + ":" + class_property_name

        itemlist = xmldoc.getElementsByTagName(tagName)

        return itemlist[0].firstChild.nodeValue


    def check_feature(self, ft_name):
        """Utility to check feature existence in wfs."""
        features = self.list_feature()

        if ft_name not in features['features']:
            raise NotFound('Feature "{}" not found'.format(ft_name))


class DataSource(metaclass=ABCMeta):
    """Abstract Class DataSource.

    :param id: DataSource id
    :type id: string.

    :param m_conninfo: Connection info
    :type m_conninfo: dict.

    """

    def __init__(self, id, m_conninfo):
        """Abstraction to make DataSource."""
        self._id = id
        self._connection_inf = m_conninfo

    def get_id(self):
        """Get datasource id."""
        return self._id

    def get_connection_info(self):
        """Get datasource info connection."""
        return self._connection_inf

    @abstractmethod
    def get_type(self):
        """Get DataSource Type."""
        pass

    @abstractmethod
    def get_trajectory(self, feature_type,temporal, x, y, obs, geom_property, classification_class,
                       start_date, end_date):
        """Get Trajectory."""
        pass


class PostGisDataSource(DataSource):
    """PostGisDataSource Class."""

    _connection_inf = {}

    def __init__(self, id, connection_info):
        """Creates PostGisDataSource."""
        super().__init__(id, connection_info)
        self.initialize()

    def initialize(self):
        """Inicialize Postgis Connection for."""
        self.open_connection()

    def get_type(self):
        """Get DataSource type."""
        return "POSTGIS"

    def open_connection(self):
        """Open Postgis connection."""
        self.pg_poll = PostGisConnectionPool(self)
        self.pg_poll.open_conection()

    def close_connection(self):
        """Close Postgis connection."""
        self.pg_poll.close_connection()
        print("Close Connection")

    def execute_query(self, sql):
        """Execute query."""
        result = self.pg_poll.execute_query(sql)

        return  result
    def get_trajectory(self, feature_type,temporal, x, y, obs, geom_property, classification_class,
                       start_date=None, end_date=None):
        """Retorn trajectory."""
        geom = Point(x, y)

        sql = "SELECT"

        where_sql = " WHERE ST_Intersects({}, ST_GeomFromText(\'{}\', {}))".format(geom_property["property_name"], geom.wkt,
                                                                                   geom_property['srid'])

        class_name = classification_class.get_name()

        class_id = classification_class.get_id()

        class_property_name = classification_class.get_class_property_name()

        temporal_type = temporal["type"]


        if(classification_class.get_type() == "Literal" and temporal_type == "STRING"):

            properties = " \'{}\' AS classe, \'{}\' AS data ".format(class_property_name, obs["temporal_property"])
            from_str = "FROM {}".format(feature_type)
            sql += properties + from_str + where_sql

            if (start_date):
                sql += " AND \'{}\' >= {}".format(obs["temporal_property"], start_date)

            if (end_date):
                sql += " AND \'{}\' <= {}".format(obs["temporal_property"], end_date)


        elif(classification_class.get_type() == "Literal" and temporal_type != "STRING"):

            properties = " \'{}\' AS classe, {} AS data ".format(class_property_name, obs["temporal_property"])
            from_str = "FROM {}".format(feature_type)
            sql += properties + from_str + where_sql

            if (start_date):
                sql += " AND {} >= {}".format(obs["temporal_property"], start_date)

            if (end_date):
                sql += " AND {} <= {}".format(obs["temporal_property"],end_date)


        elif (classification_class.get_type() != "Literal" and temporal_type == "STRING"):

            properties = " class.{} AS classe, \'{}\' AS data ".format(class_property_name, obs["temporal_property"])
            from_str = "FROM {} AS dado, {} AS class".format(feature_type, class_name)
            where_sql += " AND dado.{} = class.{} ".format(obs["class_property"], class_id)
            sql += properties + from_str + where_sql

            if (start_date):
                sql += " AND \'{}\' >= {}".format(obs["temporal_property"], start_date)

            if (end_date):
                sql += " AND \'{}\' <= {}".format(obs["temporal_property"], end_date)


        else:

            properties = " class.{} AS classe, {} AS data ".format(class_property_name, obs["temporal_property"])
            from_str = "FROM {} AS dado, {} AS class".format(feature_type, class_name)
            where_sql += " AND dado.{} = class.{} ".format(obs["class_property"], class_id)
            sql += properties + from_str + where_sql

            if (start_date):
                sql += " AND {} >= {}".format(obs["temporal_property"], start_date)

            if (end_date):
                sql += " AND {} <= {}".format(obs["temporal_property"], end_date)

        print(sql)
        # self.open_connection()

        return self.execute_query(sql)[0] if self.execute_query(sql) else None
        #
        # if(self.execute_query(sql)):
        #     result_query = self.execute_query(sql)[0]
        #
        # else:
        #     result_query = [None] * 2
        #     result_query[0] = "No Data found"
        #     result_query[1] = "No Data found"
        #
        # return result_query
        #

class WCSDataSource(DataSource):
    """WCSDataSource Class."""

    _connection_inf = {}

    def __init__(self, id, connection_info):
        """Creates WCSDataSource."""
        super().__init__(id, connection_info)

        self.wfc_poll = WCSConnectionPool(self.get_connection_info())

    def get_type(self):
        """Get DataSource type."""
        return "WCS"

    def get_trajectory(self, feature_type, temporal, x, y, obs, geom_property, classification_class,
                       start_date, end_date):
        """Retorn trajectory for ."""
        self.wfc_poll.list_collection()
        return

class WFSDataSource(DataSource):
    """WCSDataSource Class."""

    _connection_inf = {}

    def __init__(self, id, connection_info):
        """Creates WFSDataSource."""
        super().__init__(id, connection_info)

        self.wfs_poll = WFSConnectionPool(self.get_connection_info())

        print("Inicializando WFSDataSource: {}".format(self.get_id()))
    def get_type(self):
        """Get DataSource Type."""
        return "WFS"

    def get_trajectory(self, feature_type,temporal, x, y, obs, geom_property, classification_class,
                       start_date, end_date):
        """Return trajectory."""
        geom = Point(x, y)

        class_property_name = classification_class.get_class_property_name()

        class_name = classification_class.get_name()

        result = list()

        class_type = classification_class.get_type()

        args = {
                "feature_type": feature_type,
                "geom": geom,
                "geom_property": geom_property,
                "srid": geom_property['srid']
                }

        if(class_type == "Literal" and temporal["type"] == "STRING"):
            response = self.wfs_poll.get_feature(**args)

            obs_tm = get_date_from_str(obs["temporal_property"])

            if(response):
                result.append(obs["class_property_name"])
                result.append(obs_tm.strftime(temporal["string_format"]))

        elif(class_type == "Literal" and temporal["type"] != "STRING"):
            
            args['propertyName'] = "{}".format(obs["temporal_property"])

            if (start_date):
                start_date = get_date_from_str(start_date)
                args['start_date'] = "AND {} >= {}".format(obs["temporal_property"], start_date.strftime(temporal["string_format"]))
            if (end_date):
                end_date = get_date_from_str(end_date)
                args['end_date'] = "AND {} <= {}".format(obs["temporal_property"], end_date.strftime(temporal["string_format"]))

            response = self.wfs_poll.get_feature(**args)

            if(response):
                result.append(obs["class_property_name"])
                result.append(response[obs["temporal_property"]])

        elif(class_type != "Literal" and temporal["type"] == "STRING"):

            obs_temporal = get_date_from_str(obs["temporal_property"])

            if (start_date):
                start_date = get_date_from_str(start_date)
                if(start_date > obs_temporal):
                    return
            if (end_date):
                end_date = get_date_from_str(end_date)
                if(obs_temporal > end_date):
                    return

            args['propertyName'] =  "{},{}".format(obs["class_property"], obs["temporal_property"])

            response = self.wfs_poll.get_feature(**args)

            if(response):
                featureID = response[obs["class_property"]]
                classes_prop = self.wfs_poll.get_class(featureID, class_property_name, class_name)

                result.append(classes_prop)
                result.append(obs["temporal_property"])

        else:

            args['propertyName'] =  "{},{}".format(obs["class_property"], obs["temporal_property"])

            if (start_date):
                start_date = get_date_from_str(start_date)
                args['start_date'] = "AND {} >= {}".format(obs["temporal_property"], start_date.strftime(temporal["string_format"]))
            if (end_date):
                end_date = get_date_from_str(end_date)
                args['end_date'] = "AND {} <= {}".format(obs["temporal_property"], end_date.strftime(temporal["string_format"]))

            response = self.wfs_poll.get_feature(**args)

            if(response):
                featureID = response[obs["class_property"]]
                classes_prop = self.wfs_poll.get_class(featureID, class_property_name, class_name)

                result.append(classes_prop)
                result.append(response[obs["temporal_property"]])

        return result

    def open(self):
        """Open WFS Connection."""
        self.wfs_poll = WFSConnectionPool(self.get_connection_info())
        self.wfs_poll.describe_feature("deterb_amz")
        # self.wfs_poll.openConection()


        # def close(self):
        #     print("close")


class DataSourceFactory:
    """Factory for DataSource."""

    @staticmethod
    def make(dsType, id, connInfo):
        """Factory method for creates datasource."""
        factorys = {"POSTGIS": "PostGisDataSource", "WCS": "WCSDataSource", "WFS": "WFSDataSource"}
        datasource = eval(factorys[dsType])(id, connInfo)
        return datasource


class DataSourceManager:
    """DataSourceManager Class."""

    _datasources = {
        "webservice_source": [],
        "dbms_source": [],
        "file_source": []
    }

    __instance = None

    def __init__(self):
        """Virtually private constructor."""
        print("Inicializando DatasourceManager")
        if DataSourceManager.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            DataSourceManager.__instance = self
            DataSourceManager.__instance.load_all()

    @staticmethod
    def getInstance():
        """Static access method."""
        if DataSourceManager.__instance == None:
            DataSourceManager()
        return DataSourceManager.__instance

    def get_datasource(self, ds_id):
        """Get DataSource."""
        try:
            for ds_list in self._datasources.values():
                for ds in ds_list:
                    if (ds.get_id() == ds_id):
                        return ds
        except:
            return None

    def insert_datasource(self, dsType, connInfo):
        """Insert DataSource."""
        self._datasources[dsType].append(DataSourceFactory.make(connInfo["type"], connInfo["id"], connInfo))

    def load_all(self):
        """Carrega Todos os DataSources."""
        config_file = config_folder / 'wlts_config.json'

        with config_file.open()  as json_data:

            config = json_loads(json_data.read())

            if "datasources" not in config:
                raise ValueError("No datasource in json config file")
            else:
                datasources = config["datasources"]

                for dstype, datasources_info in datasources.items():
                    for ds_info in datasources_info:
                        self.insert_datasource(dstype, ds_info)


datasource_manager = DataSourceManager()
