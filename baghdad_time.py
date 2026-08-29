from datetime import datetime as real_datetime, timedelta, timezone

class BaghdadDatetimeMeta(type):
    def __instancecheck__(cls, instance):
        return isinstance(instance, real_datetime)

    def __subclasscheck__(cls, subclass):
        return issubclass(subclass, real_datetime)

class datetime(real_datetime, metaclass=BaghdadDatetimeMeta):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            # Baghdad is UTC+3
            return real_datetime.now(timezone(timedelta(hours=3))).replace(tzinfo=None)
        return real_datetime.now(tz)

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        return real_datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def strptime(cls, date_string, format):
        real_dt = real_datetime.strptime(date_string, format)
        return cls(real_dt.year, real_dt.month, real_dt.day,
                   real_dt.hour, real_dt.minute, real_dt.second,
                   real_dt.microsecond, real_dt.tzinfo)

    @classmethod
    def fromisoformat(cls, date_string):
        real_dt = real_datetime.fromisoformat(date_string)
        return cls(real_dt.year, real_dt.month, real_dt.day,
                   real_dt.hour, real_dt.minute, real_dt.second,
                   real_dt.microsecond, real_dt.tzinfo)

    @classmethod
    def combine(cls, date, time, tzinfo=True):
        real_dt = real_datetime.combine(date, time, tzinfo)
        return cls(real_dt.year, real_dt.month, real_dt.day,
                   real_dt.hour, real_dt.minute, real_dt.second,
                   real_dt.microsecond, real_dt.tzinfo)

    @classmethod
    def fromtimestamp(cls, timestamp, tz=None):
        real_dt = real_datetime.fromtimestamp(timestamp, tz)
        return cls(real_dt.year, real_dt.month, real_dt.day,
                   real_dt.hour, real_dt.minute, real_dt.second,
                   real_dt.microsecond, real_dt.tzinfo)
