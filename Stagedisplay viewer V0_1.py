import obspython as obs
import threading
from queue import Queue
import socket
import xml.etree.ElementTree as ET
import time

SUCCESSFUL_LOGIN            = "<StageDisplayLoginSuccess />";
SUCCESSFUL_LOGIN_WINDOWS    = "<StageDisplayLoginSuccess>";
INVALID_PASSWORD            = "<Error>Invalid Password</Error>"

host            = "localhost"
port            = 50002
password        = "password"
connected       = False
autoconnect     = True
thread_running  = False #if a thread for recieving data is running
disconnect      = False
disconnected    = False #If the thread should disconnect

displayLayouts      = ET
StageDisplayData    = ET

update_time    = 0
slideText      = ""
last_slideText = ""

source_1_name = ""
source_2_name = ""
transparency1 = 100
transparency2 = 0
transition_time = 0.5

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
q = Queue()
thread_lock = threading.Lock()

def connect_button_clicked(props, p):
    global connected
    global thread_running

    if not autoconnect and not thread_running:
        thread_running = True
        t = threading.Thread(target=connect)
        t.daemon = True
        t.start()
        q.put(0)
    elif connected:
        print("Already connected")
    elif thread_running:
       print("Autoconnect running")

def connect(): #run only in thread t
    q.get()
    global autoconnect
    global thread_running
    global disconnect
    global connected
    global password
    global s

    while autoconnect and thread_running and not disconnect:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            loginString = "<StageDisplayLogin>" + password + "</StageDisplayLogin>"
            print("Sending login") # + loginString)
            s.sendall(loginString.encode() + b'\r' + b'\n')

            data = s.recv(4096).decode("utf-8")
            print("Initial response from server: " + data)
            if SUCCESSFUL_LOGIN_WINDOWS in data or SUCCESSFUL_LOGIN in data:
                print("Connected")
                with thread_lock:
                    connected = True
                while connected and not disconnect:
                    recv_and_process_data()
                s.close()
                print("Disconnected")
            elif INVALID_PASSWORD in data:
                print("Login to server failed: Invalid password - Make sure the password matches the one set in Propresenter")
            else:
                print("Login to server failed: Unknown response - Make sure you're connecting to Propresenter StageDisplay server")

        except Exception as E:
            print("Couldn't connect to server: " + str(E))
            s.close()
            time.sleep(5)
        
        with thread_lock:
            connected = False
        

    thread_running = False

def recv_and_process_data(): #run only in thread t
    global connected
    global slideText
    global last_slideText
    global displayLayouts
    global source_1_name
    global source_2_name
    
    try:
        data = s.recv(4096).decode("utf-8")
        for line in data.split('<?xml version="1.0"?>'):
            if len(line) > 0:
                root = ET.fromstring(line)

                if root.tag == 'DisplayLayouts':
                    with thread_lock:
                        displayLayouts = root 
                elif root.tag == 'StageDisplayData':
                    for slide in root.findall('**[@identifier="CurrentSlide"]'):
                        tmp_slideText = slide.text.strip()
                        if tmp_slideText != slideText:
                            with thread_lock:
                                #print("changeing slideText before - tmp: " + tmp_slideText + " st: " + slideText + "lst: " + last_slideText)
                                last_slideText = slideText
                                slideText = tmp_slideText
                                #print("changeing slideText after - tmp: " + tmp_slideText + " st: " + slideText + "lst: " + last_slideText)
                                set_sources()
                                #obs.timer_add(transition, 25)
                            
    except Exception as E:
        if connected:
            print("Disconnected because of error while recieving and reading data from server: " + str(E))
        else:
            print("connection was shut down")

def set_sources(): #run only at loading and in thread t
    global update_time
    global slideText
    global last_slideText
    global source_1_name
    global source_2_name
    global transparency1
    global transparency2

    update_time = time.time()
    transparency2 = transparency1
    transparency1 = 0

    source1 = obs.obs_get_source_by_name(source_1_name)
    source2 = obs.obs_get_source_by_name(source_2_name)
    settings1 = obs.obs_data_create()
    settings2 = obs.obs_data_create()

    if source1 is not None:
        obs.obs_data_set_string(settings1, "text", slideText)
        if source2 is not None:
            obs.obs_data_set_string(settings2, "text", last_slideText)
            obs.obs_data_set_int(settings1, "opacity", transparency1)
            obs.obs_data_set_int(settings2, "opacity", transparency2)
            obs.obs_data_set_int(settings1, "outline_opacity", transparency1)
            obs.obs_data_set_int(settings2, "outline_opacity", transparency2)
        else:
            obs.obs_data_set_int(settings1, "opacity", 100)
            obs.obs_data_set_int(settings1, "outline_opacity", 100)
    elif source2 is not None:
        obs.obs_data_set_string(settings2, "text", last_slideText)
        obs.obs_data_set_int(settings1, "opacity", 0)
        obs.obs_data_set_int(settings2, "opacity", 100)
        obs.obs_data_set_int(settings1, "outline_opacity", 0)
        obs.obs_data_set_int(settings2, "outline_opacity", 100)
        

    obs.obs_source_update(source1, settings1)
    obs.obs_source_update(source2, settings2)
    obs.obs_data_release(settings1)
    obs.obs_data_release(settings2)
    obs.obs_source_release(source1)
    obs.obs_source_release(source2)

def transition():
    global update_time
    global source_1_name
    global source_2_name
    global transparency1
    global transparency2
    global transition_time

    with thread_lock:
        if transparency1 < 100:
            time_since_last_update = time.time() - update_time
            lerp = int(time_since_last_update * 100 / transition_time)

            transparency1 = lerp

            if transparency1 >= 100:
                transparency1 = 100
            
            transparency2 = 100 - lerp
            if transparency2 <= 0:
                transparency2 = 0
                #obs.timer_remove(transition)


            source1 = obs.obs_get_source_by_name(source_1_name)
            source2 = obs.obs_get_source_by_name(source_2_name)
            if source1 is not None and source2 is not None:
                settings1 = obs.obs_data_create()
                settings2 = obs.obs_data_create()
                obs.obs_data_set_int(settings1, "opacity", transparency1)
                obs.obs_data_set_int(settings2, "opacity", transparency2)
                obs.obs_data_set_int(settings1, "outline_opacity", transparency1)
                obs.obs_data_set_int(settings2, "outline_opacity", transparency2)
                obs.obs_source_update(source1, settings1)
                obs.obs_source_update(source2, settings2)
                obs.obs_data_release(settings1)
                obs.obs_data_release(settings2)
                obs.obs_source_release(source1)
                obs.obs_source_release(source2)

# defines script description 
def script_description():
   return '''Connects to Propresenter stage display server, and sets a text source as the current slides text. Make sure to set the right host IP, Port and password as in Propresenter.

Choose two individual text sources to get a fading transition.

If you don't see your text sources in the lists, try to reload the script.'''

# defines user properties
def script_properties():
    #global props 
    props = obs.obs_properties_create()

    p1 = obs.obs_properties_add_list(props, "source 1", "Text Source", obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING)
    p2 = obs.obs_properties_add_list(props, "source 2", "Text Source", obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING)
    obs.obs_property_list_add_string(p1, "None", "")
    obs.obs_property_list_add_string(p2, "None", "")

    sources = obs.obs_enum_sources()
    if sources is not None:
        for source in sources:
            source_id = obs.obs_source_get_id(source)
            if source_id == "text_gdiplus" or source_id == "text_ft2_source":
                name = obs.obs_source_get_name(source)
                obs.obs_property_list_add_string(p1, name, name)
                obs.obs_property_list_add_string(p2, name, name)
    obs.source_list_release(sources)

    obs.obs_properties_add_float_slider(props, "transition_time", "Transition time (S)", 0.1, 5.0, 0.1)

    obs.obs_properties_add_text(props, "host", "Host ip", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_int(props, "port", "Port", 1, 100000, 1)
    obs.obs_properties_add_text(props, "password", "Password", obs.OBS_TEXT_PASSWORD)
    obs.obs_properties_add_button(props, "connect_button", "Connect to server", connect_button_clicked)
    obs.obs_properties_add_bool(props, "autoconnect", "Automatically try to (re)connect to server")

    return props

# called at startup
def script_load(settings):
    global connected
    global autoconnect
    global thread_running
    global slideText
    global last_slideText
    
    #Make the text sources show nothing at startup
    slideText       = ""
    last_slideText  = ""
    set_sources()

    if autoconnect:
        thread_running = True
        t = threading.Thread(target=connect)
        t.daemon = True
        t.start()
        q.put(0)
    obs.timer_add(transition, 25)

# called when unloaded
def script_unload():
    global connected
    global thread_running
    global disconnect
    #print("unloading")
    with thread_lock:
        disconnect = True
    
    while thread_running:
    	time.sleep(0.0001)

    #print("unloaded")

# called when user updatas settings
def script_update(settings):
    global source_1_name
    global source_2_name
    global transition_time
    global host
    global port
    global password
    global autoconnect
    #global props

    source_1_name = obs.obs_data_get_string(settings, "source 1")
    source_2_name = obs.obs_data_get_string(settings, "source 2")
    # list1 = obs.obs_properties_get(props, "source 2")
    # obs.obs_property_list_item_disable(list1, 2, True)
    transition_time = obs.obs_data_get_double(settings, "transition_time")

    host = obs.obs_data_get_string(settings, "host")
    port = obs.obs_data_get_int(settings, "port")
    password = obs.obs_data_get_string(settings, "password")
    autoconnect = obs.obs_data_get_bool(settings, "autoconnect")

def script_defaults(settings):
    obs.obs_data_set_default_double(settings, "transition_time", 0.5)
    obs.obs_data_set_default_string(settings, "host", "localhost")
    obs.obs_data_set_default_int(settings, "port", 50002)
    obs.obs_data_set_default_string(settings, "password", "password")
    obs.obs_data_set_default_bool(settings, 'autoconnect', True)

# def update_source_lists():
#     sources = obs.obs_enum_sources()
#     if sources is not None:
#         for source in sources:
#             source_id = obs.obs_source_get_id(source)
#             if source_id == "text_gdiplus" or source_id == "text_ft2_source":
#                 name = obs.obs_source_get_name(source)
#                 obs.obs_property_list_add_string(p1, name, name)
#                 obs.obs_property_list_add_string(p2, name, name)
#     obs.source_list_release(sources)

# def source_create():
# 	update_source_lists()

# def source_destroy():
# 	update_source_lists()

# def source_remove():
# 	update_source_lists()

# def source_load():
# 	update_source_lists()

# def source_rename():
# 	update_source_lists()
