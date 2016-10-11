from __future__ import absolute_import
from django_alexa.api import fields, intent, ResponseBuilder

# from models import Log
from RobotThoughtApp.models import Log

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
    """
    return ResponseBuilder.create_response(
                                            message="",
                                            reprompt="",
                                            end_session=True, # should be true for audio streams
                                            title="Play Audio Stream",
                                            content="Streaming the robot logs.",
                                            directives=[
                                                ResponseBuilder.create_stream_directive(
                                                    playBehavior="REPLACE_ALL",
                                                    token="explainable-audio",
                                                    url="https://explainable-ai.herokuapp.com/audio.mp3"
                                                )
                                            ]
                                        )
