import copy
import datetime

import dateutil
import pytz


class Task(object):
    DATE_FIELDS = [
        'due', 'entry', 'modified', 'start', 'wait', 'scheduled',
    ]
    LIST_FIELDS = [
        'annotations', 'tags',
    ]
    READ_ONLY_FIELDS = [
        'id', 'uuid', 'urgency', 'entry', 'modified', 'imask',
        'resource_uri', 'start', 'status',
    ]
    STRING_FIELDS = [
        'depends', 'description', 'project', 'priority',
    ]
    KNOWN_FIELDS = DATE_FIELDS + LIST_FIELDS + STRING_FIELDS

    def __init__(self, json):
        if not json:
            raise ValueError()
        self.json = json

    @staticmethod
    def get_timezone(tzname, offset):
        if tzname is not None:
            return pytz.timezone(tzname)
        static_timezone = pytz.tzinfo.StaticTzInfo()
        static_timezone._utcoffset = datetime.timedelta(
            seconds=offset
        )
        return static_timezone

    def get_json(self):
        return self.json

    def get_safe_json(self):
        return {
            k: v for k, v in self.json.items()
            if k not in self.READ_ONLY_FIELDS
            and k in self.KNOWN_FIELDS
        }

    @classmethod
    def from_serialized(cls, data):
        data = copy.deepcopy(data)
        for key in data:
            if key in cls.DATE_FIELDS and data[key]:
                data[key] = dateutil.parser.parse(
                    data[key],
                    tzinfos=cls.get_timezone
                )
            elif key in cls.LIST_FIELDS and data[key] is None:
                data[key] = []
        return Task(data)

    def _date_from_taskw(self, value):
        value = datetime.datetime.strptime(
            value,
            '%Y%m%dT%H%M%SZ',
        )
        return value.replace(tzinfo=pytz.UTC)

    def _date_to_taskw(self, value):
        raise NotImplementedError()

    def __getattr__(self, name):
        try:
            value = self.json[name]
            if name in self.DATE_FIELDS:
                value = self._date_from_taskw(value)
            elif name == 'annotations':
                new_value = []
                for annotation in value:
                    annotation['entry'] = self._date_from_taskw(
                        annotation['entry']
                    )
                    new_value.append(annotation)
                value = new_value
            return value
        except KeyError:
            raise AttributeError()

    @property
    def id(self):
        return self.json['id'] if self.json['id'] else None

    @property
    def urgency(self):
        return float(self.json['urgency']) if self.json['urgency'] else None

    def __unicode__(self):
        return self.description
