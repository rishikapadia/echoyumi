from __future__ import absolute_import, division
from django_alexa.api import fields, intent, ResponseBuilder
from django.conf import settings
from subprocess import call
from gtts import gTTS
import os, sys, time
import pyaudio, wave
import threading
import pyttsx
import random

from RobotThoughtApp.models import Log

sys.path.append('..')
import robot_logger as audio_logger



########################
##### Main Intents #####
########################

@intent
def LaunchRequest(session):
    """
    Default Start Session Intent
    ---
    launch
    open
    resume
    start
    run
    load
    begin
    """
    messages = [
        "Hello friend! Let's get started.",
        "Howdy partner! Ready when you are.",
        "Nice to see you! Let's begin."
    ]
    audio_logger.log(random.choice(messages))
    return ResponseBuilder.create_response(message="",
                                           end_session=False)


@intent
def GetRobotThought(session):
    """
    Default GetRobotThought Intent
    ---
    what is my robot doing
    tell me what my robot is doing
    how is my robot doing
    what is the robot doing
    what is the yumi robot doing
    what is yumi doing
    what's up
    how are you doing
    speak
    continue
    end stream
    end audio
    end audio stream
    close stream
    close audio
    close audio stream
    """
    title, content = processAudio()
    return ResponseBuilder.create_response(end_session=True,
                                            title=title,
                                            content=content
                                          )


@intent
def RunInDevMode(session):
    """
    Default RunInDevMode Intent
    ---
    run in dev mode
    run dev mode
    run dev
    dev mode
    dev
    """
    global audio_thread
    if audio_thread is not None:
        stop_bluetooth_thread()
    title, content = processAudio(play_music=False)
    return ResponseBuilder.create_response(end_session=True,
                                            title=title,
                                            content=content
                                          )


@intent
def RunInResultsMode(session):
    """
    Default RunInResultsMode Intent
    ---
    run in results mode
    tell me the results
    show me the results
    results
    """
    global audio_thread
    if audio_thread is not None:
        stop_bluetooth_thread()
        title = "Stopping Audio Stream, entering Results Mode"
        content = "Stopping the Bluetooth audio stream. Reporting the results so far."
    else:
        title = "Results Mode"
        content = "Reporting the results so far."

    message = "Testing results mode."
    # total = Log.objects.filter(description__icontains="singulat").count()
    # success = Log.objects.filter(Q(description__icontains="singulat") & ~Q(description__icontains="fail")).count()
    # if total == 0:
    #     success_rate = 0.0
    # else:
    #     success_rate = 100.0 * success / total

    # message = "%d percent success rate on singulation."

    file_path = os.path.join(settings.STATIC_ROOT, 'data.csv')
    file = open(file_path, "rb")

    header = file.readline()
    header = header.strip().split(',')
    success_column_index = header.index('human_label')

    # Skip second line
    _ = file.readline()

    successes = 0
    total = 0
    for line in file:
        values = line.split(',')
        if values[success_column_index] == '1':
            successes += 1
        total += 1

    file.close()

    if total == 0:
        success_rate = 0
    else:
        success_rate = int(100.0 * successes / total + 0.5) # 0.5 is to round the percentage

    message = "We were successfully able to singulate " + str(success_rate) + " percent of the time!"

    return ResponseBuilder.create_response(message=message,
                                            end_session=True,
                                            title=title,
                                            content=content
                                          )




def processAudio(play_music=True):
    global audio_thread
    if audio_thread is not None:
        stop_bluetooth_thread()
        title = "Stopping Audio Stream"
        content = "Stopping the Bluetooth audio stream."
    else:
        start_bluetooth_thread(play_music)
        title = "Playing Audio Stream"
        content = "Streaming the robot logs via Bluetooth."
    return title, content




#############################
##### Main Audio Thread #####
#############################

class AudioThread(threading.Thread):
    def __init__(self, play_music=True):
        super(AudioThread, self).__init__()
        self._stop_event = threading.Event()
        self.play_music = play_music

        self.CHUNK = 1024
        file_path = os.path.join(settings.STATIC_ROOT, 'song.wav')
        self.wf = wave.open(file_path, 'rb')
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format = self.p.get_format_from_width(self.wf.getsampwidth()),
            channels = self.wf.getnchannels(),
            rate = self.wf.getframerate(),
            output = True
        )

        Log.objects.filter(reported=False).update(reported=True)
        self.engine = pyttsx.init()
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('voice', 'english-us')
        self.engine.startLoop(False)
        return

    def stop(self):
        self._stop_event.set()
        return

    def stopped(self):
        return self._stop_event.isSet()

    def get_music(self, chunk_size):
        data = self.wf.readframes(chunk_size)
        if len(data) < chunk_size:
            self.wf.rewind()
            data += self.wf.readframes(chunk_size - len(data))
        return data

    def merge_audio(self, data1, weight1, data2, weight2):
        # http://stackoverflow.com/questions/4039158/mixing-two-audio-files-together-with-python
        def bin_to_int(bin):
            as_int = 0
            for char in bin[::-1]: # iterate over each char in reverse (because little-endian)
                as_int <<= 8
                as_int += ord(char)
            return as_int
        def int_to_bin(as_int):
            as_bin = ''
            while as_int > 0:
                as_bin += chr(as_int % 2**8)
                as_int >>= 8
            return as_bin

        samples1 = [data1[i:i+2] for i in xrange(0, len(data1), 2)]
        samples2 = [data2[i:i+2] for i in xrange(0, len(data2), 2)]

        samples1 = [bin_to_int(s) for s in samples1]
        samples2 = [bin_to_int(s) for s in samples2]

        samples_avg = [int((s1*weight1 + s2*weight2)/(weight1 + weight2)) for (s1, s2) in zip(samples1, samples2)]

        data = [int_to_bin(s) for s in samples_avg]
        data = ''.join(data)

        return data

    def play_message(self, message):
        if message[:7] == "effect_":
            file_path = os.path.join(settings.STATIC_ROOT, 'effects', message + '.wav')
        else:
            file_path = os.path.join(settings.STATIC_ROOT, 'messages', message.lower().replace(" ", "_").replace('/', '_')+'.wav')
        if os.path.isfile(file_path):
            wf = wave.open(file_path, 'rb')
            msg_data = wf.readframes(sys.maxint)
            music_data = self.get_music(len(msg_data))
            # data = self.merge_audio(msg_data, 2.0, music_data, 1.0)
            data = msg_data
            self.stream.write(data)
        else:
            self.engine.say(message)
            self.engine.iterate()
            # spawn thread to convert message to wav file
            start_gtts_thread(message)
            while self.engine.isBusy():
                time.sleep(0.5)
        return

    def run(self):
        while not self.stopped():
            logs = Log.objects.filter(reported=False)
            if len(logs) == 0 and not self.play_music:
                time.sleep(0.01)
            elif len(logs) == 0 and self.play_music:
                data = self.get_music(self.CHUNK)
                self.stream.write(data)
            else:
                log = logs.latest('id')
                message = log.description
                Log.objects.filter(reported=False).update(reported=True)
                self.play_message(message)
        self.engine.endLoop()
        self.engine.stop()
        self.stream.close()
        self.p.terminate()
        return



audio_thread = None

def start_bluetooth_thread(play_music=True):
    global audio_thread
    audio_thread = AudioThread(play_music)
    audio_thread.daemon = True
    audio_thread.start()
    return

def stop_bluetooth_thread():
    global audio_thread
    if audio_thread is not None:
        audio_thread.stop()
        audio_thread = None
    return




##################################
##### gTTS Conversion Thread #####
##################################

def gtts_to_wav(message):
    tts = gTTS(text=message, lang='en')
    file_name = message.lower().replace(" ", "_").replace('/', '_')
    file_path = os.path.join(settings.STATIC_ROOT, 'messages', file_name)
    tts.save(file_path + ".mp3")
    call(["ffmpeg", "-i", file_path + ".mp3",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "24000",
        file_path + ".wav"])
    os.remove(file_path + ".mp3")
    return

def audify_database():
    database = [str(a['description']).lower().replace('/', ' ') for a in Log.objects.values('description')]
    database = set(database)
    saved = [a[:-4].replace('_', ' ') for a in os.listdir(os.path.join(settings.STATIC_ROOT, 'messages'))]
    saved = set(saved)
    
    messages = database - saved
    for message in messages:
        gtts_to_wav(message)
    return

def start_gtts_thread(message):
    gtts_thread = threading.Thread(target=gtts_to_wav, args=(message,))
    gtts_thread.daemon = True
    gtts_thread.start()
    return

audify_database()



############################
##### Grasping Intents #####
############################

COLORS = ("orange", "red", "white", "yellow", "gold", "black", "pink", "blue")

COLOR_TO_PART_NAME = {
    "orange": "bar_clamp",
    "red": "vase",
    "white": "part3",
    "yellow": "pawn",
    "gold": "part1",
    "black": "gearbox",
    "pink": "turbine_housing",
    "blue": "nozzle"
}


class GraspOneSlots(fields.AmazonSlots):
    paramOne = fields.AmazonCustom(label="LIST_OF_COLORS", choices=COLORS)

class GraspTwoSlots(GraspOneSlots):
    paramTwo = fields.AmazonCustom(label="LIST_OF_COLORS", choices=COLORS)

class GraspThreeSlots(GraspTwoSlots):
    paramThree = fields.AmazonCustom(label="LIST_OF_COLORS", choices=COLORS)

class GraspFourSlots(GraspThreeSlots):
    paramFour = fields.AmazonCustom(label="LIST_OF_COLORS", choices=COLORS)


@intent(slots=GraspOneSlots)
def GraspOne(session, paramOne):
    return log_grasps(1, [paramOne])

@intent(slots=GraspTwoSlots)
def GraspTwo(session, paramOne, paramTwo):
    return log_grasps(2, [paramOne, paramTwo])

@intent(slots=GraspThreeSlots)
def GraspThree(session, paramOne, paramTwo, paramThree):
    return log_grasps(3, [paramOne, paramTwo, paramThree])

@intent(slots=GraspFourSlots)
def GraspFour(session, paramOne, paramTwo, paramThree, paramFour):
    return log_grasps(4, [paramOne, paramTwo, paramThree, paramFour])


@intent
def GraspAll(session):
    return log_grasps("all", ["all"])


def log_grasps(number, params):
    if params[0] == "all":
        parts = params
    else:
        parts = [COLOR_TO_PART_NAME[c] for c in params]
    line = ','.join(parts).lower()
    
    # Write to file
    f = open("/home/autolab/Workspace/rishi_working/echoyumi/grasp_command.txt", 'w')
    f.write(line)
    f.close()

    return ResponseBuilder.create_response(end_session=True,
            title="Grasp "+str(number),
            content="Grasping "+str(number)+" items"
        )





###############################
##### Calibration Intents #####
###############################

calibration_step = 0

@intent
def Calibrate(session):
    global calibration_step
    end_session = False

    # cd Workspace/jeff_working/alan
        # changed to Workspace/jeff_working/perception
    # source activate alan
    base_command = "cd ~/Workspace/jeff_working/perception && source activate alan_michael && "

    if calibration_step == 0:
        message = "I can help you with that! First, align the checkerboard so "
        message += "that it is pushed against the robot's base. "
        message += "The tab on the checkerboard should be flush with the robot. "
        message += "Let me know when you are ready for the next step."
    elif calibration_step == 1:
        # python tools/register_camera.py
        command = base_command + "python tools/register_camera.py"
        call(command.split(" "), shell=True)
        message = "Now align the bottom right corner of the amazon box with the angled markings. "
        message += "Place the checkerboard inside the box in the same corner."
    elif calibration_step == 2:
        # python tools/register_object.py amazon_box
        command = base_command + "python tools/register_object.py amazon_box"
        call(command.split(" "), shell=True)
        command = base_command + "cd ../dex-net/ && "
        command += "python tools/calibrate_box_crop.py data/experiments/amazon_box_tesla_11_07_16/grasp_experiment.yaml"
        call(command.split(" "), shell=True)
        # cd ../dex-net/
        # python tools/calibrate_box_crop.py data/experiments/amazon_box_tesla_11_07_16/grasp_experiment.yaml
        message = "Now look at the screen. "
        message += "Can you see anything besides the inside of the box in the image? "
        message += "If so, you will need to modify the yamel file to crop out the border. "
        message += "Otherwise, continue to the next step."
    elif calibration_step == 3:
        # python scripts/amazon_grasps.py data/experiments/amazon_box_tesla_11_07_16/
        command = base_command + "python scripts/amazon_grasps.py data/experiments/amazon_box_tesla_11_07_16/"
        call(command.split(" "), shell=True)
        message = "And now you're all done! Happy developing!"
        end_session = True

    calibration_step += 1    
    title = "Calibrating, step " + str(calibration_step)
    response = ResponseBuilder.create_response(
            message=message,
            end_session=end_session,
            title=title,
            content=title
        )

    calibration_step %= 4
    return response



###################################
##### Data Collection Intents #####
###################################


DATA_COMMANDS = ("start", "record", "stop", "pause", "finish", "capture", "take")

class DataCollectionSlots(fields.AmazonSlots):
    command = fields.AmazonCustom(label="DATA_COMMANDS", choices=DATA_COMMANDS)

@intent(slots=DataCollectionSlots)
def DataCollection(session, command):

    if command not in DATA_COMMANDS:
        return ResponseBuilder.create_response(end_session=True,
                title="Data Collection Commands FAILED!",
                content=str(command)
            )
    
    if command == "finish":
        return ResponseBuilder.create_response(end_session=True,
                title="Data Collection Commands finished",
                content=str(command)
            )

    # Write to file
    f = open("/home/autolab/Workspace/rishi_working/echoyumi/data_command.txt", 'w')
    f.write(command)
    f.close()

    return ResponseBuilder.create_response(end_session=True,
            title="Data Collection Commands",
            content=str(command)
        )


# Overwriting the above function to test without using the external robot program
# to actually record the camera images and robot arm poses
ITERATION_NUMBER = 0
STEP_NUMBER = 0

messages_per_iteration = [
    [
        "Step 1: Please place the object in the workspace and capture an image.",
        "Step 2 is through, now run step 1."
    ],
    [
        "Step 2: Please guide my arm to the object and record my arm's pose.",
        "Step 1 is done, now do step 2."
    ]
]

data_messages = [
    "That's odd, I can't see the object anymore. Did you move it outside of the workspace?",
    "Good for you! That was your fastest yet.",
    "Oh no! The gripper is too low. Let's try that again.",
    "Now we're on a roll! Only 5 more to go.",
    "That was a bit slower than before. Can we try to go faster?",
    "Only a few more and you can beat the lab time record!",
    "Well done! You've collected 20 samples in record time. Hey where did you learn to do this?"
]

@intent(slots=DataCollectionSlots)
def DataCollection(session, command):
    global ITERATION_NUMBER, STEP_NUMBER

    if command not in DATA_COMMANDS:
        audio_logger.log("I did not recognize that command")
        return ResponseBuilder.create_response(end_session=True,
                title="Data Collection Commands FAILED!",
                content=str(command)
            )

    if STEP_NUMBER == 0:
        audio_logger.log("effect_step_1")
    elif (STEP_NUMBER == 1) and ((ITERATION_NUMBER == 6) or (ITERATION_NUMBER == 8)):
        audio_logger.log("effect_error")
    elif STEP_NUMBER == 1:
        audio_logger.log("effect_step_2")
    time.sleep(0.05)

    if ITERATION_NUMBER < 4:
        audio_logger.log(messages_per_iteration[STEP_NUMBER][int(ITERATION_NUMBER / 2.0)])
    elif (ITERATION_NUMBER > 5) and (STEP_NUMBER == 1) and (ITERATION_NUMBER - 6 < len(data_messages)):
        # words of encouragement, speed prompts, iteration progress, etc.
        audio_logger.log(data_messages[ITERATION_NUMBER - 6])

    if STEP_NUMBER == 1:
        ITERATION_NUMBER += 1
    STEP_NUMBER = 1 - STEP_NUMBER

    message = str(command) + " - Iteration #"+str(ITERATION_NUMBER+1)+", Step #"+str(STEP_NUMBER+1)
    return ResponseBuilder.create_response(end_session=True,
            title="Data Collection Demo",
            content=message
        )






########################################
##### EchoBot Ring-Stacking Intent #####
########################################


STACKING_COMMANDS = [
    "right closed",
    "right opened",
    "right closed",
    "left closed",
    "right opened",
    "right closed",
    "left opened",
    "left closed",
    "left opened",
    "right opened"
]
stacking_step = 0
experiment_id = -1



DIRECTIONS = ("left", "right")
STATUSES = ("opened", "closed")

class RingStackingSlots(fields.AmazonSlots):
    direction = fields.AmazonCustom(label="LIST_OF_DIRECTIONS", choices=DIRECTIONS)
    status = fields.AmazonCustom(label="LIST_OF_STATUSES", choices=STATUSES)

@intent(slots=RingStackingSlots)
def RingStacking(session, direction, status):
    global stacking_step
    end_session = False

    if direction not in DIRECTIONS:
        message = "Sorry? I did not understand the first word."
        log_to_file("Error in direction")
        audio_logger.log(message)
        return ResponseBuilder.create_response(end_session=end_session, title="Misunderstood direction", content=message)
    if status not in STATUSES:
        message = "Sorry? I did not understand the second word."
        log_to_file("Error in status")
        audio_logger.log(message)
        return ResponseBuilder.create_response(end_session=end_session, title="Misunderstood status", content=message)

    # Main logic:
    command = str(direction) + " " + str(status)
    if command == STACKING_COMMANDS[stacking_step] and (stacking_step != len(STACKING_COMMANDS)-1):
        log_to_file("Step "+str(stacking_step)+" completed")
        title = "Step "+str(stacking_step)
        stacking_step += 1
        audio_logger.log("effect_step_1")
        return ResponseBuilder.create_response(end_session=end_session, title=title)
    if command != STACKING_COMMANDS[stacking_step]:
        log_to_file("Error")
        content = "step: " + str(stacking_step) + ", command: " + str(command)
        stacking_step = 0
        # message = "Error. Restart trial."

        message = random.choice([
            "That's not quite right. Let's reset the sequence and try that again.",
            "That's not what I expected. Let's restart the demonstration."
        ])
        audio_logger.log("effect_error")
        time.sleep(0.05)
        audio_logger.log(message)
        return ResponseBuilder.create_response(end_session=end_session, title="Human Error", content=content)


    if stacking_step == len(STACKING_COMMANDS) - 1:
        log_to_file("Success")
        # message = "Success!"
        message = random.choice([
            "You figured it out!",
            "All done! You're really good at this!",
            "Well done! You made it look easy!",
            "Congratulations! You've finished the experiment.",
            "Well aren't you a problem solver! Good work!"
        ])
        audio_logger.log("effect_success")
        time.sleep(0.05)
        audio_logger.log(message)
        end_session = True
        stacking_step = 0
        return ResponseBuilder.create_response(end_session=end_session, title="Success", content=message)

    message = "This error should not be reachable!"
    audio_logger.log(message)
    return ResponseBuilder.create_response(end_session=end_session, title=message, content=message)


@intent
def RestartRingStacking(session):
    global stacking_step
    stacking_step = 0
    log_to_file("Restarting")
    message = "Restarted. Please continue from the beginning."
    audio_logger.log(message)
    return ResponseBuilder.create_response(end_session=False, title="Restarting", content=message)



class StartNewTrialSlots(fields.AmazonSlots):
    exp_id = fields.AmazonNumber()

@intent(slots=StartNewTrialSlots)
def StartNewTrial(session, exp_id):
    global experiment_id
    experiment_id = exp_id
    log_to_file("Starting trial")
    message = "Starting trial "+str(experiment_id)
    audio_logger.log(message)
    return ResponseBuilder.create_response(end_session=False, title=message, content=message)




def log_to_file(status):
    file_path = "/home/autolab/Workspace/rishi_working/experiment2_logs.csv"
    if not os.path.exists(file_path):
        f = open(file_path,'w')
        header = ["experiment_id", "uses_echobot", "timestamp", "status"]
        f.write(",".join(header))
        f.write('\n')
        f.close()

    f = open(file_path, 'a')
    row = [experiment_id, True, time.time(), status]
    row = [str(i) for i in row]
    f.write(",".join(row))
    f.write('\n')
    f.close()
    return


