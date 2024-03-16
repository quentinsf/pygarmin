"""fit.py: Contains the FIT class which is used to encode fit files."""

from datetime import datetime
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.course_message import CourseMessage
from fit_tool.profile.messages.course_point_message import CoursePointMessage
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.user_profile_message import UserProfileMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
import fit_tool.profile.profile_type as profile_type
from . import logger as mod_logger


class FIT:
    _intensity = {'active': profile_type.Intensity.ACTIVE,
                  'rest': profile_type.Intensity.REST,
                  }

    _lap_trigger = {'manual': profile_type.LapTrigger.MANUAL,
                    'distance': profile_type.LapTrigger.DISTANCE,
                    'location': profile_type.LapTrigger.POSITION_START,
                    'time': profile_type.LapTrigger.TIME,
                    'heart_rate': profile_type.LapTrigger.FITNESS_EQUIPMENT,
                    }

    _sport = {'running': profile_type.Sport.RUNNING,
              'biking': profile_type.Sport.CYCLING,
              'other': profile_type.Sport.GENERIC,
              }

    _duration_type = {'time': profile_type.WorkoutStepDuration.TIME,
                      'distance': profile_type.WorkoutStepDuration.DISTANCE,
                      'heart rate less than': profile_type.WorkoutStepDuration.HR_LESS_THAN,
                      'heart rate greater than': profile_type.WorkoutStepDuration.HR_GREATER_THAN,
                      'calories burned': profile_type.WorkoutStepDuration.CALORIES,
                      'open': profile_type.WorkoutStepDuration.OPEN,
                      'repeat': profile_type.WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT,
                      }

    _target_type = {'speed': profile_type.WorkoutStepTarget.SPEED,
                    'heart rate': profile_type.WorkoutStepTarget.HEART_RATE,
                    'open': profile_type.WorkoutStepTarget.OPEN,
                    }

    _course_point_type = {'generic': profile_type.CoursePoint.GENERIC,
                          'summit': profile_type.CoursePoint.SUMMIT,
                          'valley': profile_type.CoursePoint.VALLEY,
                          'water': profile_type.CoursePoint.WATER,
                          'food': profile_type.CoursePoint.FOOD,
                          'danger': profile_type.CoursePoint.DANGER,
                          'left': profile_type.CoursePoint.LEFT,
                          'right': profile_type.CoursePoint.RIGHT,
                          'straight': profile_type.CoursePoint.STRAIGHT,
                          'first_aid': profile_type.CoursePoint.FIRST_AID,
                          'fourth_category': profile_type.CoursePoint.FOURTH_CATEGORY,
                          'third_category': profile_type.CoursePoint.THIRD_CATEGORY,
                          'second_category': profile_type.CoursePoint.SECOND_CATEGORY,
                          'first_category': profile_type.CoursePoint.FIRST_CATEGORY,
                          'hors_category': profile_type.CoursePoint.HORS_CATEGORY,
                          'sprint': profile_type.CoursePoint.SPRINT,
                          }

    def file_id_message(self):
        message = FileIdMessage()
        message.type = profile_type.FileType.ACTIVITY
        message.manufacturer = profile_type.Manufacturer.GARMIN
        message.product = self.gps.product_id
        message.serial_number = self.gps.unit_id
        message.time_created = self.timestamp
        return message

    def start_event_message(self, start_timestamp):
        message = EventMessage()
        message.event = profile_type.Event.TIMER
        message.event_type = profile_type.EventType.START
        message.timestamp = start_timestamp
        return message

    def stop_event_message(self, stop_timestamp):
        message = EventMessage()
        message.event = profile_type.Event.TIMER
        message.eventType = profile_type.EventType.STOP_ALL
        message.timestamp = stop_timestamp
        return message

    def workout_message(self, workout):
        workout_message = WorkoutMessage()
        workout_message.workoutName = workout.get_name()
        workout_message.sport = self._sport.get(workout.get_sport_type())
        workout_message.num_valid_steps = workout.num_valid_steps
        return workout_message

    def workout_steps(self, steps):
        step_messages = []
        for step in steps:
            step_message = WorkoutStepMessage()
            step_message.workout_step_name = step.get_custom_name()
            step_message.intensity = self._intensity.get(step.get_intensity())
            step_message.duration_type = self._duration_type.get(step.get_duration_type())
            step_message.duration_value = step.duration_value
            step_message.target_type = self._target_type.get(step.get_target_type())
            # Garmin describes time in seconds, FIT in milliseconds
            step_message.target_value = step.target_value * 1000 if step.get_target_type() == 'time' else step.target_value
            step_message.custom_target_value_low = step.target_custom_zone_low
            step_message.custom_target_value_high = step.target_custom_zone_high
            step_messages.append(step_message)
        return step_messages


class FITActivity(FIT):

    def __init__(self, gps, activity):
        self.gps = gps
        self.activity = activity
        self.num_sessions = len(self.activity)
        self.sessions = [session for session in self.activity]
        self.timestamp = round(datetime.now().astimezone().timestamp() * 1000)

    def build(self):
        builder = FitFileBuilder(auto_define=True, min_string_size=50)
        builder.add(self.file_id_message())
        builder.add(self.device_info_message())
        for session in self.sessions:
            run = session[0]
            laps = session[1]
            track = session[2]
            start_timestamp = round(track[1].get_datetime().astimezone().timestamp() * 1000)
            stop_timestamp = round(track[-1].get_datetime().astimezone().timestamp() * 1000)
            timestamp = stop_timestamp
            total_time = sum([lap.total_time for lap in laps])
            total_distance = sum([lap.total_dist for lap in laps])
            builder.add(self.start_event_message(start_timestamp))
            builder.add_all(self.lap_message(laps))
            builder.add_all(self.record_message(track))
            if run.has_workout():
                workout = run.get_workout()
                builder.add(self.workout_message(workout))
                if workout.num_valid_steps:
                    steps = workout.get_steps()[:workout.num_valid_steps]
                    builder.add_all(self.workout_steps(steps))
            builder.add(self.session_message(run, start_timestamp, stop_timestamp, total_time, total_distance))
            builder.add(self.stop_event_message(stop_timestamp))
        builder.add(self.activity_message(stop_timestamp))
        return builder.build()

    def device_info_message(self):
        message = DeviceInfoMessage()
        message.manufacturer = profile_type.Manufacturer.GARMIN
        message.serial_number = self.gps.unit_id
        message.product = self.gps.product_id
        message.software_version = self.gps.software_version
        message.descriptor = self.gps.product_description
        return message

    def activity_message(self, timestamp):
        message = ActivityMessage()
        message.num_sessions = self.num_sessions
        message.timestamp = timestamp
        return message

    def session_message(self, run, start_timestamp, stop_timestamp, total_time, total_distance):
        message = SessionMessage()
        message.timestamp = stop_timestamp
        message.start_time = start_timestamp
        message.total_elapsed_time = total_time
        message.total_timer_time = total_time
        message.total_distance = total_distance
        message.sport = self._sport.get(run.get_sport_type())
        return message

    def lap_message(self, laps):
        messages = []
        for lap in laps:
            message = LapMessage()
            message.message_index = lap.index
            message.start_time = round(lap.get_start_datetime().astimezone().timestamp()) * 1000
            message.total_elapsed_time = lap.total_time
            message.total_timer_time = lap.total_time
            message.timestamp = message.start_time + message.total_elapsed_time
            message.total_distance = lap.total_dist
            if lap.get_begin().is_valid():
                message.begin_position_lat = lap.get_begin().as_degrees().lat
                message.begin_position_long = lap.get_begin().as_degrees().lon
            if lap.get_end().is_valid():
                message.end_position_lat = lap.get_end().as_degrees().lat
                message.end_position_long = lap.get_end().as_degrees().lon
            if lap.is_valid_avg_heart_rate():
                message.avg_heart_rate = lap.avg_heart_rate
            if lap.is_valid_max_heart_rate():
                message.max_heart_rate = lap.max_heart_rate
            message.intensity = self._intensity.get(lap.get_intensity())
            if lap.is_valid_avg_cadence():
                message.avg_cadence = lap.avg_cadence
            messages.append(message)
        return messages

    def record_message(self, track):
        messages = []
        # Loop over track points excluding the track header
        for track_point in track[1:]:
            if not track_point.is_valid_time() or not track_point.get_posn().is_valid():
                continue
            message = RecordMessage()
            message.timestamp = round(track_point.get_datetime().astimezone().timestamp()) * 1000
            mod_logger.log.info(f"Date and time: {track_point.get_datetime().astimezone().isoformat()}")
            message.position_lat = track_point.get_posn().as_degrees().lat
            message.position_long = track_point.get_posn().as_degrees().lon
            mod_logger.log.info(f"Latitude: {message.position_lat}")
            mod_logger.log.info(f"Longitude: {message.position_long}")
            if track_point.is_valid_alt():
                message.altitude = track_point.alt
                mod_logger.log.info(f"Altitude: {message.altitude}")
            if track_point.is_valid_heart_rate():
                message.heart_rate = track_point.heart_rate
                mod_logger.log.info(f"Heart rate: {message.heart_rate}")
            if track_point.is_valid_distance():
                message.distance = track_point.distance
                mod_logger.log.info(f"Distance: {track_point.distance}")
            if track_point.is_valid_cadence():
                message.cadence = track_point.cadence
                mod_logger.log.info(f"Cadence: {message.cadence}")
            messages.append(message)
        return messages


class FITWorkout(FIT):

    def __init__(self, gps, workout):
        self.gps = gps
        self.workout = workout
        self.num_steps = self.workout.num_valid_steps
        self.steps = self.workout.get_steps()[:self.num_steps]
        self.timestamp = round(datetime.now().astimezone().timestamp() * 1000)

    def build(self):
        builder = FitFileBuilder(auto_define=True, min_string_size=50)
        builder.add(self.file_id_message())
        builder.add(self.workout_message(self.workout))
        if self.num_steps:
            builder.add_all(self.workout_steps(self.steps))
        return builder.build()


class FITCourse(FIT):
    """Course File Messages"""

    def __init__(self, gps, course):
        self.gps = gps
        self.course = course
        self.timestamp = round(datetime.now().astimezone().timestamp() * 1000)

    def build(self):
        course = self.course[0]
        course_laps = self.course[1]
        course_track = self.course[2]
        course_points = self.course[3]
        builder = FitFileBuilder(auto_define=True, min_string_size=50)
        builder.add(self.file_id_message())
        builder.add(self.course_message())
        builder.add_all(self.lap_message(self.course_laps))
        start_timestamp = round(self.course_track[1].get_datetime().astimezone().timestamp()) * 1000
        stop_timestamp = round(self.course_track[-1].get_datetime().astimezone().timestamp()) * 1000
        builder.add(self.start_event_message(start_timestamp))
        builder.add_all(self.record_message(self.course_track))
        builder.add_all(self.course_point_message(self.course_points))
        builder.add(self.stop_event_message(stop_timestamp))
        return builder.build()

    def course_message(self):
        message = CourseMessage()
        message.courseName = self.course.get_course_name()
        return message

    def lap_message(self, course_laps):
        messages = []
        for lap in course_laps:
            message = LapMessage()
            message.message_index = lap.lap_index
            message.total_timer_time = lap.total_time
            message.total_distance = lap.total_dist
            if lap.get_begin().is_valid():
                message.begin_position_lat = lap.get_begin().as_degrees().lat
                message.begin_position_long = lap.get_begin().as_degrees().lon
            if lap.get_end().is_valid():
                message.end_position_lat = lap.get_end().as_degrees().lat
                message.end_position_long = lap.get_end().as_degrees().lon
            if lap.is_valid_avg_heart_rate():
                message.avg_heart_rate = lap.avg_heart_rate
            if lap.is_valid_max_heart_rate():
                message.max_heart_rate = lap.max_heart_rate
            message.intensity = self._intensity.get(lap.get_intensity())
            if lap.is_valid_avg_cadence():
                message.avg_cadence = lap.avg_cadence
            messages.append(message)
        return messages

    def course_point_message(self, course_points):
        messages = []
        for course_point in course_points:
            message = CoursePointMessage()
            message.timestamp = round(course_point.get_track_point_datetime().astimezone().timestamp()) * 1000
            message.course_point_name = course_point.get_name()
            message.type = self._course_point_type.get(course_point.get_point_type())
            messages.append(message)
        return messages
