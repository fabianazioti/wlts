#
# This file is part of Web Land Trajectory Service.
# Copyright (C) 2019-2020 INPE.
#
# Web Land Trajectory Service is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""WLTS DataSource Abstract Collection."""
from abc import ABCMeta, abstractmethod


class DataSource(metaclass=ABCMeta):
    """Abstract Class DataSource.

    :param id: DataSource identification
    :type id: string.
    """

    def __init__(self, id):
        """Abstraction to make DataSource."""
        self._id = id

    @property
    def get_id(self):
        """Get datasource id."""
        return self._id

    @abstractmethod
    def get_type(self):
        """Get DataSource Type."""
        pass
