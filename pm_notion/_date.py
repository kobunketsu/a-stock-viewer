import datetime
from enum import Enum

def isEarlyThanToday(str_date):
    date1 = datetime.datetime.strptime(str_date, "%Y-%m-%d").date()
    date2 = datetime.datetime.now().date()

    if date1 < date2:
        # print(f"{date1} is earlier than {date2}")
        return True
    elif date1 == date2:
        # print(f"{date1} is the same as {date2}")
        return False
    else:
        # print(f"{date1} is later than {date2}")
        return False

# Define an enum with time intervals and their corresponding `replace` arguments
class TimeInterval(Enum):
    YEAR = {'month': 1, 'day': 1, 'hour': 0, 'minute': 0, 'second': 0, 'microsecond': 0}
    MONTH = {'day': 1, 'hour': 0, 'minute': 0, 'second': 0, 'microsecond': 0}
    DAY = {'hour': 0, 'minute': 0, 'second': 0, 'microsecond': 0}
    HOUR = {'minute': 0, 'second': 0, 'microsecond': 0}
    MINUTE = {'second': 0, 'microsecond': 0}
    SECOND = {'microsecond': 0}