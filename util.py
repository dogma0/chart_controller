import chart_cache as cc
import intervaltree
import pandas as pd
import statistics as stats


VALID_RESOLUTIONS = {60, 300, 3600}
SECONDS_IN_MIN = 60
SECONDS_IN_HOUR = 60 * SECONDS_IN_MIN
SECONDS_IN_DAY = 24 * SECONDS_IN_HOUR
SECONDS_IN_WEEK = 7 * SECONDS_IN_DAY


def time_stamp(t):
    if type(t) == int:
        epoch_time = t
        return pd.to_datetime(epoch_time, unit='s')
    elif type(t) == str:
        return pd.to_datetime(t)
    elif isinstance(t, pd.Timestamp):
        return t
    else:
        raise ValueError("Invalid time representation")


def epoch(timestamp):
    if isinstance(timestamp, str):
        timestamp = pd.Timestamp(timestamp)
    return (timestamp - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')


def list_tointerval(start_time, end_time, data_resolution, data):
    if isinstance(start_time, int) or isinstance(start_time, str):
        start_time = time_stamp(start_time)
    if isinstance(end_time, int) or isinstance(end_time, str):
        end_time = time_stamp(end_time)

    dates = pd.date_range(
                start_time,
                end_time,
                freq=pd.offsets.Second(data_resolution)
            )[:-1]
    dataframe = pd.DataFrame(data, index=dates, columns=['temperature'])
    period = intervaltree.Interval(
        time_stamp(start_time),
        time_stamp(end_time),
            cc.IntervalData(
            data_resolution,
            time_stamp(start_time),
            time_stamp(end_time),
            dataframe
        ))

    return period


def resolution(duration):
    '''Resolution (in seconds) for the given duration.
    '''
    two_h = 2 * SECONDS_IN_HOUR
    one_w = SECONDS_IN_WEEK

    # duration for the period mapping to the correct resolution according
    # to business rule
    resolution_by_rule = {
        (0, two_h): SECONDS_IN_MIN,
        (two_h, one_w): 5 * SECONDS_IN_MIN,
        (one_w, float('inf')): SECONDS_IN_HOUR
    }

    for (lower_limit, upper_limit), resolution in resolution_by_rule.items():
        if lower_limit <= duration and duration < upper_limit:
            return resolution
    raise ValueError('Cannot accept negative value for duration')


def num_datapoints(duration, data_resolution=None):
    '''It is guaranteed that resolution divides duration acorrding to the requirement.
    '''
    if not data_resolution:
        data_resolution = resolution(duration)
    return int(duration / data_resolution)


def rolledup_data(old_data, group_size):
    return [
        stats.mean(old_data[i:i + group_size])
        for i in range(0, len(old_data), group_size)
    ]


def extrapolated_data(old_data, factor):
    return [v for sublist in [[v] * factor for v in old_data] for v in sublist]


def scaled_data(old_data, old_resolution, new_resolution):
    '''Given array of numbers, roll up or extrapolate data depending on the
    ratio of old_resolution to new_resolution
    '''
    if old_resolution not in VALID_RESOLUTIONS or new_resolution not in VALID_RESOLUTIONS:
        raise ValueError('''Input resolution is not a correct resolution,
this is likely a bug.''')
    if old_resolution == new_resolution:
        return old_data
    elif old_resolution < new_resolution:
        return rolledup_data(old_data, int(new_resolution / old_resolution))
    else:
        return extrapolated_data(old_data,
                                 int(old_resolution / new_resolution))


def period_data_splitter(iv, is_lower, point):
    data = iv.data
    if not data:
        return None
    if is_lower:
        return cc.IntervalData(data.resolution, data.start_time, point,
                          data.dataframe[:point][:-1])
    else:
        return cc.IntervalData(data.resolution, point, data.end_time,
                          data.dataframe[point:])


def period_data_reducer(data_earlier, data_later):
    ''' Merge periods that are equal in start and end time,
    and keep the higher resolution version
    '''
    if data_earlier.resolution <= data_later.resolution:
        return data_earlier
    else:
        return data_later


def period_data_combinator(data_earlier, data_later):
    ''' Combine the data of two periods of the same resolution that are adjacent to each other
    '''
    assert data_earlier.resolution == data_later.resolution

    return cc.IntervalData(
        data_earlier.resolution, data_earlier.start_time, data_later.end_time,
        pd.concat([data_earlier.dataframe, data_later.dataframe]))
