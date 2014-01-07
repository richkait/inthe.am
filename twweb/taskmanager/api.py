import datetime
from functools import wraps
import json
import logging
import operator
import pytz

from tastypie import authentication, authorization, bundle, fields, resources

from django.conf.urls import url
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpRequest

from . import models


logger = logging.getLogger(__name__)


def dropbox_reader(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        try:
            # Normal Views
            user = args[0].user
        except IndexError:
            # Tastypie Views
            user = kwargs['bundle'].request.user
        store = models.TaskStore.get_for_user(user)
        store.download_files_from_dropbox()
        kwargs['store'] = store
        return f(self, *args, **kwargs)
    return wrapper


def dropbox_writer(f):
    def wrapper(self, *args, **kwargs):
        try:
            # Normal Views
            user = args[0].user
        except IndexError:
            # Tastypie Views
            user = kwargs['bundle'].request.user
        store = models.TaskStore.get_for_user(user)
        store.download_files_from_dropbox()
        kwargs['store'] = store
        result = f(self, *args, **kwargs)
        store.upload_files_to_dropbox()
        return result
    return wrapper


class UserAuthorization(authorization.Authorization):
    def read_list(self, object_list, bundle):
        return object_list.filter(
            pk=bundle.request.user.pk
        )

    def read_detail(self, object_list, bundle):
        return bundle.obj == bundle.request.user


class UserResource(resources.ModelResource):
    def prepend_urls(self):
        return [
            url(
                r"^(?P<resource_name>%s)/status/?$" % (
                    self._meta.resource_name
                ),
                self.wrap_view('account_status')
            ),
        ]

    def account_status(self, request, **kwargs):
        if request.user.is_authenticated():
            store = request.user.task_stores
            user_data = {
                'logged_in': True,
                'uid': request.user.pk,
                'username': request.user.username,
                'name': (
                    request.user.first_name
                    if request.user.first_name
                    else request.user.username
                ),
                'email': request.user.email,
                'dropbox_configured': store.filter(configured=True).exists()
            }
        else:
            user_data = {
                'logged_in': False,
            }
        return HttpResponse(
            json.dumps(user_data),
            content_type='application/json',
        )

    class Meta:
        queryset = User.objects.all()
        authorization = UserAuthorization()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']


class Task(object):
    def __init__(self, json):
        self.json = json

    def __getattr__(self, name):
        try:
            value = self.json[name]
            if name in ['due', 'entry', 'modified', 'start']:
                value = datetime.datetime.strptime(
                    value,
                    '%Y%m%dT%H%M%SZ',
                )
                value = value.replace(tzinfo=pytz.UTC)
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


class TaskResource(resources.Resource):
    id = fields.IntegerField(attribute='id', null=True)
    uuid = fields.CharField(attribute='uuid')
    description = fields.CharField(attribute='description')
    due = fields.DateTimeField(attribute='due', null=True)
    entry = fields.DateTimeField(attribute='entry', null=True)
    modified = fields.DateTimeField(attribute='modified', null=True)
    priority = fields.CharField(attribute='priority', null=True)
    start = fields.DateTimeField(attribute='start', null=True)
    status = fields.CharField(attribute='status')
    urgency = fields.FloatField(attribute='urgency')
    depends = fields.CharField(attribute='depends', null=True)

    def prepend_urls(self):
        return [
            url(
                r"^(?P<resource_name>%s)/autoconfigure/?$" % (
                    self._meta.resource_name
                ),
                self.wrap_view('autoconfigure')
            ),
            url(
                r"^(?P<resource_name>%s)/configure/?$" % (
                    self._meta.resource_name
                ),
                self.wrap_view('configure')
            ),
            url(
                r"^(?P<resource_name>%s)/(?P<uuid>[\w\d_.-]+)/complete/?$" % (
                    self._meta.resource_name
                ),
                self.wrap_view('complete')
            ),
            url(
                r"^(?P<resource_name>%s)/(?P<uuid>[\w\d_.-]+)/delete/?$" % (
                    self._meta.resource_name
                ),
                self.wrap_view('delete')
            )
        ]

    @dropbox_writer
    def complete(self, request, uuid, store, **kwargs):
        store.client.task_done(uuid=uuid)
        return HttpResponse(
            status=200
        )

    def delete(self, request, uuid, **kwargs):
        return HttpResponse(
            status=501
        )

    def autoconfigure(self, request, **kwargs):
        store = models.TaskStore.get_for_user(request.user)
        try:
            store.autoconfigure_dropbox()
        except models.NoTaskFoldersFound:
            return HttpResponse(
                json.dumps({
                    'error': 'No task folder found',
                }),
                status=404,
                content_type='application/json',
            )
        except models.MultipleTaskFoldersFound:
            return HttpResponse(
                json.dumps({
                    'error': 'Multiple task folders found',
                    'options': store.find_dropbox_folders()
                }),
                status=409,
                content_type='application/json',
            )
        return HttpResponse(
            json.dumps({
                'status': 'Successfully configured'
            }),
            status=200,
            content_type='application/json',
        )

    def configure(self, request, **kwargs):
        store = models.TaskStore.get_for_user(request.user)
        options = store.find_dropbox_folders()
        try:
            path = request.GET['path']
        except KeyError:
            return HttpResponse(
                json.dumps({
                    'error': 'No task folder selected',
                    'options': options
                }),
                status=400,
                content_type='application/json',
            )
        if path not in options:
            return HttpResponse(
                json.dumps({
                    'error': '%s is not a valid task folder' % (
                        path
                    ),
                    'options': options
                }),
                status=422,
                content_type='application/json',
            )
        store.configure_dropbox(path)
        return HttpResponse(
            json.dumps({
                'status': 'Successfully configured'
            }),
            status=200,
            content_type='application/json',
        )

    def _get_store(self, user):
        return user.task_stores.get()

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}

        if isinstance(bundle_or_obj, bundle.Bundle):
            kwargs['pk'] = bundle_or_obj.obj.uuid
        else:
            kwargs['pk'] = bundle_or_obj.uuid

        return kwargs

    def apply_sorting(self, obj_list, options=None):
        if options is None:
            options = {}

        parameter_name = 'order_by'

        if hasattr(options, 'getlist'):
            order_bits = options.getlist(parameter_name)
        else:
            order_bits = options.get(parameter_name)

            if not isinstance(order_bits, list, tuple):
                order_bits = [order_bits]

        if not order_bits:
            order_bits = ['-urgency']

        order_by_args = []
        for order_by in order_bits:
            order_by_bits = order_by.split(',')

            field_name = order_by_bits[0]
            reverse = False

            if order_by_bits[0].startswith('-'):
                field_name = order_by_bits[0][1:]
                reverse = True

            order_by_args.append(
                (field_name, reverse)
            )

        order_by_args.reverse()
        for arg, reverse in order_by_args:
            obj_list = sorted(
                obj_list,
                key=operator.attrgetter(arg),
                reverse=reverse,
            )

        return obj_list

    @dropbox_reader
    def obj_get_list(self, bundle, store, **kwargs):
        if hasattr(bundle.request, 'GET'):
            filters = bundle.request.GET.copy()
        filters.update(kwargs)

        key = 'pending'
        if int(bundle.request.GET.get('completed', 0)):
            key = 'completed'

        objects = []
        for task_json in store.client.load_tasks()[key]:
            objects.append(
                Task(task_json)
            )

        return objects

    @dropbox_reader
    def obj_get(self, bundle, store, **kwargs):
        return Task(store.client.get_task(uuid=kwargs['pk'])[1])

    class Meta:
        authentication = authentication.SessionAuthentication()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        limit = 1000
        max_limit = 1000
