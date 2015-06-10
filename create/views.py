from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse

from servers.models import Compute
from create.models import Flavor
from instance.models import Instance

from libvirt import libvirtError

from vrtManager.create import wvmCreate
from vrtManager import util
from create.forms import FlavorAddForm, NewVMForm

# added by Ankush on 03/06

import logging
from ConfigParser import SafeConfigParser

logger = logging.getLogger(__name__)
init_parser = SafeConfigParser()
init_parser.read('configuration_files/init_config.ini')
master = init_parser.get('initialize','master')

logger.info("Registered Master user of framework: "+master)


def create(request, host_id):
    """
    Create new instance.
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    conn = None
    errors = []
    storages = []
    networks = []
    meta_prealloc = False
    compute = Compute.objects.get(id=host_id)
    flavors = Flavor.objects.filter().order_by('id')

    try:
        conn = wvmCreate(compute.hostname,
                         compute.login,
                         compute.password,
                         compute.type)

        storages = sorted(conn.get_storages())
        networks = sorted(conn.get_networks())
        instances = conn.get_instances()
        get_images = sorted(conn.get_storages_images())
        mac_auto = util.randomMAC()
    except libvirtError as err:
        errors.append(err)
    logger.info("User:"+request.user.username+" is trying to create a VM on host: "+compute.hostname)    
    if request.user.username != master:
         msg = _("You don't have the permission to perform this operation");
         errors.append(msg)
    elif conn:
        if not storages:
            msg = _("You haven't defined have any storage pools")
            errors.append(msg)
        if not networks:
            msg = _("You haven't defined have any network pools")
            errors.append(msg)

        if request.method == 'POST':
            if 'create_flavor' in request.POST:
                form = FlavorAddForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    if request.user.username == master: 
                         create_flavor = Flavor(label=data['label'],
                                                vcpu=data['vcpu'],
                                                memory=data['memory'],
                                                disk=data['disk'])
                         create_flavor.save()
                         logger.info("User:"+request.user.username+" is trying to create a VM labelled: "+data['label']+", on host: "+compute.hostname)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to perform this operation")
                         error.append(msg)
            if 'delete_flavor' in request.POST:
                flavor_id = request.POST.get('flavor', '')
                delete_flavor = Flavor.objects.get(id=flavor_id)
                logger.info("Delete flavor called by user!");
                delete_flavor.delete()
                return HttpResponseRedirect(request.get_full_path())
            if 'create_xml' in request.POST:
                xml = request.POST.get('from_xml', '')
                try:
                    name = util.get_xml_path(xml, '/domain/name')
                    logger.info("User:"+request.user.username+" is using XML file at: "+name)
                except util.libxml2.parserError:
                    name = None
                if name in instances:
                    msg = _("A virtual machine with this name already exists")
                    logger.info("User:"+request.user.username+" attempt failed as a VM with same name exists already")
                    errors.append(msg)
                else:
                    try:
                        conn._defineXML(xml)
                        return HttpResponseRedirect(reverse('instance', args=[host_id, name]))
                    except libvirtError as err:
                        errors.append(err.message)
            if 'create' in request.POST:
                volumes = {}
                form = NewVMForm(request.POST)
                if form.is_valid():
                    data = form.cleaned_data
                    logger.info("User:"+request.user.username+" is trying to create a VM labelled: "+data['name']+", on host: "+compute.hostname)
                    if data['meta_prealloc']:
                        meta_prealloc = True
                    if instances:
                        if data['name'] in instances:
                            logger.info("User:"+request.user.username+" attempt failed as a VM with same name exists already")
                            msg = _("A virtual machine with this name already exists")
                            errors.append(msg)
                    if not errors:
                        if data['hdd_size']:
                            if not data['mac']:
                                logger.info("User:"+request.user.username+" attempt failed as a VM MAC addess not present")
                                msg = _("No Virtual Machine MAC has been entered")
                                errors.append(msg)
                            else:
                                try:
                                    path = conn.create_volume(data['storage'], data['name'], data['hdd_size'],
                                                              metadata=meta_prealloc)
                                    volumes[path] = conn.get_volume_type(path)
                                    logger.info("User:"+request.user.username+" has volume created at "+path)
                                except libvirtError as msg_error:
                                    errors.append(msg_error.message)
                        elif data['template']:
                            templ_path = conn.get_volume_path(data['template'])
                            clone_path = conn.clone_from_template(data['name'], templ_path, metadata=meta_prealloc)
                            volumes[clone_path] = conn.get_volume_type(clone_path)
                        else:
                            if not data['images']:
                                msg = _("First you need to create or select an image")
                                errors.append(msg)
                            else:
                                for vol in data['images'].split(','):
                                    try:
                                        path = conn.get_volume_path(vol)
                                        volumes[path] = conn.get_volume_type(path)
                                    except libvirtError as msg_error:
                                        errors.append(msg_error.message)
                        if not errors:
                            uuid = util.randomUUID()
                            try:
                                conn.create_instance(data['name'], data['memory'], data['vcpu'], data['host_model'],
                                                     uuid, volumes, data['networks'], data['virtio'], data['mac'])
                                create_instance = Instance(compute_id=host_id, name=data['name'], uuid=uuid,owner=request.user.username)
                                create_instance.save()
                                logger.info("User:"+request.user.username+" , a new instance = "+data['name']+", has been created")
                                return HttpResponseRedirect(reverse('instance', args=[host_id, data['name']]))
                            except libvirtError as err:
                                if data['hdd_size']:
                                    conn.delete_volume(volumes.keys()[0])
                                errors.append(err)

        conn.close()

    return render_to_response('create.html', locals(), context_instance=RequestContext(request))
