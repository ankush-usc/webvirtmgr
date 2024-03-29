from string import letters, digits
from random import choice
from bisect import insort

from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect, HttpResponse
from django.template import RequestContext
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
import json
import time

from instance.models import Instance
from servers.models import Compute

from vrtManager.instance import wvmInstances, wvmInstance

from libvirt import libvirtError, VIR_DOMAIN_XML_SECURE
from webvirtmgr.settings import TIME_JS_REFRESH, QEMU_KEYMAPS, QEMU_CONSOLE_TYPES

# added by Ankush 03/06
import logging
from ConfigParser import SafeConfigParser

init_parser = SafeConfigParser()
init_parser.read('configuration_files/init_config.ini')

logger = logging.getLogger(__name__)
master = init_parser.get('initialize','master')  #initializing the master control for the framework
logger.info("Master of the framework interface is: "+master)

per_user = init_parser.get('initialize','per_user_view') == '1'
logger.info("The view is limited to per-user view: "+ str(per_user))

def instusage(request, host_id, vname):
    """
    Return instance usage
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    cookies = {}
    datasets = {}
    datasets_rd = []
    datasets_wr = []
    json_blk = []
    cookie_blk = {}
    blk_error = False
    datasets_rx = []
    datasets_tx = []
    json_net = []
    cookie_net = {}
    net_error = False
    points = 5
    curent_time = time.strftime("%H:%M:%S")
    compute = Compute.objects.get(id=host_id)
    cookies = request._get_cookies()
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"

    try:
        conn = wvmInstance(compute.hostname,
                           compute.login,
                           compute.password,
                           compute.type,
                           vname)
        cpu_usage = conn.cpu_usage()
        blk_usage = conn.disk_usage()
        net_usage = conn.net_usage()
        conn.close()

        if cookies.get('cpu') == '{}' or not cookies.get('cpu') or not cpu_usage:
            datasets['cpu'] = [0]
            datasets['timer'] = [curent_time]
        else:
            datasets['cpu'] = eval(cookies.get('cpu'))
            datasets['timer'] = eval(cookies.get('timer'))

        datasets['timer'].append(curent_time)
        datasets['cpu'].append(int(cpu_usage['cpu']))

        if len(datasets['timer']) > points:
            datasets['timer'].pop(0)
        if len(datasets['cpu']) > points:
            datasets['cpu'].pop(0)

        cpu = {
            'labels': datasets['timer'],
            'datasets': [
                {
                    "fillColor": "rgba(241,72,70,0.5)",
                    "strokeColor": "rgba(241,72,70,1)",
                    "pointColor": "rgba(241,72,70,1)",
                    "pointStrokeColor": "#fff",
                    "data": datasets['cpu']
                }
            ]
        }

        for blk in blk_usage:
            if cookies.get('hdd') == '{}' or not cookies.get('hdd') or not blk_usage:
                datasets_wr.append(0)
                datasets_rd.append(0)
            else:
                datasets['hdd'] = eval(cookies.get('hdd'))
                try:
                    datasets_rd = datasets['hdd'][blk['dev']][0]
                    datasets_wr = datasets['hdd'][blk['dev']][1]
                except:
                    blk_error = True

            if not blk_error:
                datasets_rd.append(int(blk['rd']) / 1048576)
                datasets_wr.append(int(blk['wr']) / 1048576)

                if len(datasets_rd) > points:
                    datasets_rd.pop(0)
                if len(datasets_wr) > points:
                    datasets_wr.pop(0)

                disk = {
                    'labels': datasets['timer'],
                    'datasets': [
                        {
                            "fillColor": "rgba(83,191,189,0.5)",
                            "strokeColor": "rgba(83,191,189,1)",
                            "pointColor": "rgba(83,191,189,1)",
                            "pointStrokeColor": "#fff",
                            "data": datasets_rd
                        },
                        {
                            "fillColor": "rgba(249,134,33,0.5)",
                            "strokeColor": "rgba(249,134,33,1)",
                            "pointColor": "rgba(249,134,33,1)",
                            "pointStrokeColor": "#fff",
                            "data": datasets_wr
                        },
                    ]
                }

            json_blk.append({'dev': blk['dev'], 'data': disk})
            cookie_blk[blk['dev']] = [datasets_rd, datasets_wr]

        for net in net_usage:
            if cookies.get('net') == '{}' or not cookies.get('net') or not net_usage:
                datasets_rx.append(0)
                datasets_tx.append(0)
            else:
                datasets['net'] = eval(cookies.get('net'))
                try:
                    datasets_rx = datasets['net'][net['dev']][0]
                    datasets_tx = datasets['net'][net['dev']][1]
                except:
                    net_error = True

            if not net_error:
                datasets_rx.append(int(net['rx']) / 1048576)
                datasets_tx.append(int(net['tx']) / 1048576)

                if len(datasets_rx) > points:
                    datasets_rx.pop(0)
                if len(datasets_tx) > points:
                    datasets_tx.pop(0)

                network = {
                    'labels': datasets['timer'],
                    'datasets': [
                        {
                            "fillColor": "rgba(83,191,189,0.5)",
                            "strokeColor": "rgba(83,191,189,1)",
                            "pointColor": "rgba(83,191,189,1)",
                            "pointStrokeColor": "#fff",
                            "data": datasets_rx
                        },
                        {
                            "fillColor": "rgba(151,187,205,0.5)",
                            "strokeColor": "rgba(151,187,205,1)",
                            "pointColor": "rgba(151,187,205,1)",
                            "pointStrokeColor": "#fff",
                            "data": datasets_tx
                        },
                    ]
                }

            json_net.append({'dev': net['dev'], 'data': network})
            cookie_net[net['dev']] = [datasets_rx, datasets_tx]

        data = json.dumps({'cpu': cpu, 'hdd': json_blk, 'net': json_net})
        response.cookies['cpu'] = datasets['cpu']
        response.cookies['timer'] = datasets['timer']
        response.cookies['hdd'] = cookie_blk
        response.cookies['net'] = cookie_net
        response.write(data)
    except libvirtError:
        data = json.dumps({'error': 'Error 500'})
        response.write(data)
    return response


def inst_status(request, host_id, vname):
    """
    Instance block
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    compute = Compute.objects.get(id=host_id)

    try:
        conn = wvmInstance(compute.hostname,
                           compute.login,
                           compute.password,
                           compute.type,
                           vname)
        status = conn.get_status()
        conn.close()
    except libvirtError:
        status = None

    data = json.dumps({'status': status})
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(data)
    return response


def insts_status(request, host_id):
    """
    Instances block
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    errors = []
    instances = []
    compute = Compute.objects.get(id=host_id)

    try:
        conn = wvmInstances(compute.hostname,
                            compute.login,
                            compute.password,
                            compute.type)
        get_instances = conn.get_instances()
    except libvirtError as err:
        errors.append(err)
    logger.info("User: "+request.user.username+", is quering instance info")
    for instance in get_instances:
        instances.append({'name': instance,
                          'status': conn.get_instance_status(instance),
                          'memory': conn.get_instance_memory(instance),
                          'vcpu': conn.get_instance_vcpu(instance),
                          'uuid': conn.get_uuid(instance),
                          'host': host_id,
                          'dump': conn.get_instance_managed_save_image(instance)
                          })

    data = json.dumps(instances)
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(data)
    return response


def instances(request, host_id):
    """
    Instances block
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    errors = []
    instances = []
    time_refresh = 8000
    get_instances = []
    conn = None
    compute = Compute.objects.get(id=host_id)

    try:
        conn = wvmInstances(compute.hostname,
                            compute.login,
                            compute.password,
                            compute.type)
        get_instances = conn.get_instances()
    except libvirtError as err:
        errors.append(err)

    for instance in get_instances:
        try:
            inst = Instance.objects.get(compute_id=host_id, name=instance)
            uuid = inst.uuid
        except Instance.DoesNotExist:
            uuid = conn.get_uuid(instance)
            inst = Instance(compute_id=host_id, name=instance, uuid=uuid,owner=request.user.username)
            inst.save()
        if not per_user or request.user.username == master or (per_user and request.user.username in instance): 
            inst_own = Instance.objects.get(compute_id=host_id, name=instance)
            logger.info("Owner of VM: "+instance+" is User: "+inst_own.owner)
            instances.append({'name': instance,
                              'status': conn.get_instance_status(instance),
                              'uuid': uuid,
                              'memory': conn.get_instance_memory(instance),
                              'vcpu': conn.get_instance_vcpu(instance),
                              'has_managed_save_image': conn.get_instance_managed_save_image(instance)})

    if conn:
        try:
            if request.method == 'POST':
                name = request.POST.get('name', '')
                if 'start' in request.POST:
                    if request.user.username in name or request.user.username == master:
                         logger.info("User:"+request.user.username+", is starting instance = "+name)
                         conn.start(name)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to start VM instance = "+name);
                         errors.append(msg)
                if 'shutdown' in request.POST:
                    logger.info("User:"+request.user.username+", is shutting down instance = "+name)
                    if request.user.username in name or request.user.username == master:
                         conn.shutdown(name)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to shutdown the VM: "+name)
                         errors.append(msg)
                if 'destroy' in request.POST:
                    logger.info("User:"+request.user.username+", is destroying instance = "+name)
                    if request.user.username != master or request.user.username in name:
                         msg = _("You don't have the permission to perform this operation: ")
                         errors.append(msg)     
                    else:
                        conn.force_shutdown(name)
                        return HttpResponseRedirect(request.get_full_path())
                if 'managedsave' in request.POST:
                    logger.info("User:"+request.user.username+", is destroying(managed-save) instance = "+name)
                    if request.user.username in name or request.user.username == master: 
                        conn.managedsave(name)
                        return HttpResponseRedirect(request.get_full_path())
                    else:
                        msg = _("You don't have the permission to do this operation")
                        errors.append(msg)
                if 'deletesaveimage' in request.POST:
                    logger.info("User:"+request.user.username+", is destroying(deleting saved image as well) instance = "+name)
                    if request.user.username == master:
                         conn.managed_save_remove(name)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to do this operation")
                         errors.append(msg)
                if 'suspend' in request.POST:
                    logger.info("User:"+request.user.username+", is suspending instance = "+name)
                    if request.user.username in name or request.user.username == master:
                         conn.suspend(name)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to do this operation")
                         errors.append(msg)
                if 'resume' in request.POST:
                    logger.info("User:"+request.user.username+", is resuming instance = "+name)
                    if request.user.username in name or request.user.username == master:
                         conn.resume(name)
                         return HttpResponseRedirect(request.get_full_path())
                    else:
                         msg = _("You don't have the permission to do this operation")
                         errors.append(msg)
            conn.close()
        except libvirtError as err:
            errors.append(err)
    return render_to_response('instances.html', locals(), context_instance=RequestContext(request))


def instance(request, host_id, vname):
    """
    Instance block
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('login'))

    def show_clone_disk(disks):
        clone_disk = []
        for disk in disks:
            if disk['image'] is None:
                continue
            if disk['image'].count(".") and len(disk['image'].rsplit(".", 1)[1]) <= 7:
                name, suffix = disk['image'].rsplit(".", 1)
                image = name + "-clone" + "." + suffix
            else:
                image = disk['image'] + "-clone"
            clone_disk.append(
                {'dev': disk['dev'], 'storage': disk['storage'], 'image': image, 'format': disk['format']})
        return clone_disk

    errors = []
    messages = []
    time_refresh = TIME_JS_REFRESH * 3
    compute = Compute.objects.get(id=host_id)
    computes = Compute.objects.all()
    computes_count = len(computes)
    keymaps = QEMU_KEYMAPS
    console_types = QEMU_CONSOLE_TYPES

    try:
        conn = wvmInstance(compute.hostname,
                           compute.login,
                           compute.password,
                           compute.type,
                           vname)

        status = conn.get_status()
        autostart = conn.get_autostart()
        vcpu = conn.get_vcpu()
        cur_vcpu = conn.get_cur_vcpu()
        uuid = conn.get_uuid()
        memory = conn.get_memory()
        cur_memory = conn.get_cur_memory()
        description = conn.get_description()
        disks = conn.get_disk_device()
        media = conn.get_media_device()
        networks = conn.get_net_device()
        media_iso = sorted(conn.get_iso_media())
        vcpu_range = conn.get_max_cpus()
        memory_range = [256, 512, 768, 1024, 2048, 4096, 6144, 8192, 16384]
        if memory not in memory_range:
            insort(memory_range, memory)
        if cur_memory not in memory_range:
            insort(memory_range, cur_memory)
        memory_host = conn.get_max_memory()
        vcpu_host = len(vcpu_range)
        telnet_port = conn.get_telnet_port()
        console_type = conn.get_console_type()
        console_port = conn.get_console_port()
        console_keymap = conn.get_console_keymap()
        snapshots = sorted(conn.get_snapshot(), reverse=True)
        inst_xml = conn._XMLDesc(VIR_DOMAIN_XML_SECURE)
        has_managed_save_image = conn.get_managed_save_image()
        clone_disks = show_clone_disk(disks)
        console_passwd = conn.get_console_passwd()

        try:
            instance = Instance.objects.get(compute_id=host_id, name=vname)
            if instance.uuid != uuid:
                instance.uuid = uuid
                instance.save()
        except Instance.DoesNotExist:
            instance = Instance(compute_id=host_id, name=vname, uuid=uuid,owner=request.user.username)
            instance.save()

        if request.method == 'POST':
            if 'start' in request.POST:
                logger.info("User:"+request.user.username+", is starting instance = "+vname)
                if request.user.username in vname or request.user.username == master:
                     conn.start()
                     return HttpResponseRedirect(request.get_full_path() + '#shutdown')
                else:
                     msg = _("You don't have the permission to do this operation")
                     errors.append(msg)
            if 'power' in request.POST:
                if 'shutdown' == request.POST.get('power', ''):
                    logger.info("User:"+request.user.username+", is shutting-down instance = "+vname)
                    if request.user.username in vname or request.user.username == master:
                         conn.shutdown()
                         return HttpResponseRedirect(request.get_full_path() + '#shutdown')
                    else:
                         msg = _("You don't have the permission to shutdown instance = "+vname)
                         errors.append(msg); 
                if 'destroy' == request.POST.get('power', ''):
                    logger.info("User:"+request.user.username+", is issuing a force shutdown to instance = "+vname)
                    if request.user.username == master or request.user.username in vname:
                         conn.force_shutdown()
                         return HttpResponseRedirect(request.get_full_path() + '#forceshutdown')
                    else:
                         msg = _("You don't have the permission to do this operation")
                         errors.append(msg)
                if 'managedsave' == request.POST.get('power', ''):
                    logger.info("User:"+request.user.username+", is destroying(managed-save) instance = "+vname)
                    if request.user.username == master:
                         conn.managedsave()
                         return HttpResponseRedirect(request.get_full_path() + '#managedsave')
                    else:
                         msg = _("You don't have the permission to do this operation")
                         errors.append(msg)
            if 'deletesaveimage' in request.POST:
                logger.info("User:"+request.user.username+", is destroying(delete image) instance = "+vname)
                if request.user.username == master:
                     conn.managed_save_remove()
                     return HttpResponseRedirect(request.get_full_path() + '#managedsave')
                else:
                     msg = _("You don't have the permission to do this operation")
                     errors.append(msg)
            if 'suspend' in request.POST:
                logger.info("User:"+request.user.username+", is suspending instance = "+vname)
                if request.user.username in vname or request.user.username == master:
                     conn.suspend()
                     return HttpResponseRedirect(request.get_full_path() + '#suspend')
                else:
                     msg = _("You cannot suspend other user VM:"+vname)
                     errors.append(msg)
            if 'resume' in request.POST:
                logger.info("User:"+request.user.username+", is resuming instance = "+vname)
                if request.user.username in vname or request.user.username == master:
                      conn.resume()
                      return HttpResponseRedirect(request.get_full_path() + '#suspend')
                else:
                       msg = _("You cannot resume other user VM:"+vname)
                       errors.append(msg)
            if 'delete' in request.POST:
                if request.user.username == master:
                    if conn.get_status() == 1:
                        conn.force_shutdown()
                    try:
                        instance = Instance.objects.get(compute_id=host_id, name=vname)
                        logger.info("User:"+request.user.username+", is deleting VM: " +vname)
                        instance.delete()
                        if request.POST.get('delete_disk', ''):
                            conn.delete_disk()
                    finally:
                        conn.delete()
                    return HttpResponseRedirect(reverse('instances', args=[host_id]))
                else:
                     msg = _("You don't have the permission to do this operation")
                     errors.append(msg)
            if 'snapshot' in request.POST:
                name = request.POST.get('name', '')
                logger.info("User:"+request.user.username+", is creating snapshot = "+name)
                if request.user.username in name or request.user.username == master:
                     conn.create_snapshot(name)
                     return HttpResponseRedirect(request.get_full_path() + '#istaceshapshosts')
                else:
                     msg = _("You cannot perform this operation in other user VM:"+name)
                     errors.append(msg)
            if 'umount_iso' in request.POST:
                logger.info("User:"+request.user.username+", is unmounting iso image ")
                if request.user.username == master:
                     image = request.POST.get('path', '')
                     dev = request.POST.get('umount_iso', '')
                     conn.umount_iso(dev, image)
                     return HttpResponseRedirect(request.get_full_path() + '#instancemedia')
                else:
                     msg = _("You don't have the permission to execute this operation");
                     errors.append(msg)
            if 'mount_iso' in request.POST:
                logger.info("User:"+request.user.username+", is mounting iso image")
                if request.user.username == master:
                     image = request.POST.get('media', '')
                     dev = request.POST.get('mount_iso', '')
                     conn.mount_iso(dev, image)
                     return HttpResponseRedirect(request.get_full_path() + '#instancemedia')
                else:
                     msg = _("You don't have the permission to execute this operation")
                     errors.append(msg)

# Currently, adding all the cases to be executed only with root privilege, but we might have to split operations on different privileges. 
#Though inefficient, following condition is coded on purpose.

            if 'change_settings' in request.POST or 'change_xml' in request.POST or 'clone' in request.POST or 'set_autostart' in request.POST or 'unset_autostart' in request.POST or 'set_console_passwd' in request.POST or 'set_console_keymap' in request.POST or 'set_console_type' in request.POST or 'migrate' in request.POST or 'delete_snapshot' in request.POST or 'revert_snapshot' in request.POST:
              if request.user.username == master:
                if 'change_settings' in request.POST:
                    description = request.POST.get('description', '')
                    vcpu = request.POST.get('vcpu', '')
                    cur_vcpu = request.POST.get('cur_vcpu', '')
                    memory = request.POST.get('memory', '')
                    memory_custom = request.POST.get('memory_custom', '')
                    if memory_custom:
                        memory = memory_custom
                    cur_memory = request.POST.get('cur_memory', '')
                    cur_memory_custom = request.POST.get('cur_memory_custom', '')
                    if cur_memory_custom:
                        cur_memory = cur_memory_custom
                    logger.info("User:"+request.user.username+", is changing settings; new max memory = "+memory+" and new allocated  memory = "+cur_memory+" and cpus = "+vcpu)
                    conn.change_settings(description, cur_memory, memory, cur_vcpu, vcpu)
                    return HttpResponseRedirect(request.get_full_path() + '#instancesettings')
                if 'change_xml' in request.POST:
                    logger.info("User:"+request.user.username+", is changing the xml definition for VM")
                    xml = request.POST.get('inst_xml', '')
                    if xml:
                        conn._defineXML(xml)
                        return HttpResponseRedirect(request.get_full_path() + '#instancexml')
                if 'clone' in request.POST:
                    clone_data = {}
                    clone_data['name'] = request.POST.get('name', '')

                    for post in request.POST:
                        if 'disk' or 'meta' in post:
                            clone_data[post] = request.POST.get(post, '')
                    logger.info("User:"+request.user.username+", issued clone request");
                    conn.clone_instance(clone_data)
                    return HttpResponseRedirect(reverse('instance', args=[host_id, clone_data['name']]))
                if 'set_autostart' in request.POST:
                    logger.info("User:"+request.user.username+", is issuing autostart operation on instance = "+vname)
                    conn.set_autostart(1)
                    return HttpResponseRedirect(request.get_full_path() + '#instancesettings')
                if 'unset_autostart' in request.POST:
                    logger.info("User:"+request.user.username+", is revoking autostart operation on instance = "+vname)
                    conn.set_autostart(0)
                    return HttpResponseRedirect(request.get_full_path() + '#instancesettings')
                if 'set_console_passwd' in request.POST:
                    if request.POST.get('auto_pass', ''):
                        passwd = ''.join([choice(letters + digits) for i in xrange(12)])
                    else:
                        passwd = request.POST.get('console_passwd', '')
                        clear = request.POST.get('clear_pass', False)
                        if clear:
                            passwd = ''
                        if not passwd and not clear:
                            msg = _("Enter the console password or select Generate")
                            errors.append(msg)
                    if not errors:
                        if not conn.set_console_passwd(passwd):
                            msg = _("Error setting console password. You should check that your instance have an graphic device.")
                            errors.append(msg)
                        else:
                            return HttpResponseRedirect(request.get_full_path() + '#console_pass')
                
                if 'set_console_keymap' in request.POST:
                    keymap = request.POST.get('console_keymap', '')
                    clear = request.POST.get('clear_keymap', False)
                    if clear:
                        conn.set_console_keymap('')
                    else:
                        conn.set_console_keymap(keymap)
                    return HttpResponseRedirect(request.get_full_path() + '#console_keymap')
                if 'set_console_type' in request.POST:
                    console_type = request.POST.get('console_type', '')
                    logger.info("User:"+request.user.username+", is modifying console type to "+console_type);
                    conn.set_console_type(console_type)
                    return HttpResponseRedirect(request.get_full_path() + '#console_type')
                if 'migrate' in request.POST:
                    compute_id = request.POST.get('compute_id', '')
                    live = request.POST.get('live_migrate', False)
                    unsafe = request.POST.get('unsafe_migrate', False)
                    xml_del = request.POST.get('xml_delete', False)
                    new_compute = Compute.objects.get(id=compute_id)
                    conn_migrate = wvmInstances(new_compute.hostname,
                                                new_compute.login,
                                                new_compute.password,
                                                new_compute.type)
                    logger.info("User:"+request.user.username+", issued a migrate request with instance: "+vname);
                    conn_migrate.moveto(conn, vname, live, unsafe, xml_del)
                    conn_migrate.define_move(vname)
                    conn_migrate.close()
                    return HttpResponseRedirect(reverse('instance', args=[compute_id, vname]))

                if 'delete_snapshot' in request.POST:
                    snap_name = request.POST.get('name', '')
                    logger.info("User:"+request.user.username+", initiated delete-request for snapshot: "+snap_name)
                    conn.snapshot_delete(snap_name)
                    return HttpResponseRedirect(request.get_full_path() + '#istaceshapshosts')
                if 'revert_snapshot' in request.POST:
                    snap_name = request.POST.get('name', '')
                    logger.info("User:"+request.user.username+", is reverting snapshot: "+snap_name)
                    conn.snapshot_revert(snap_name)
                    msg = _("Successful revert snapshot: ")
                    msg += snap_name
                    messages.append(msg)

              else:
                    logger.info("User:"+request.user.username+", is changing the settings for VM: "+vname)
                    msg = _("You don't have the permission to execute this operation")
                    errors.append(msg) 

        conn.close()

    except libvirtError as err:
        errors.append(err)

    return render_to_response('instance.html', locals(), context_instance=RequestContext(request))
