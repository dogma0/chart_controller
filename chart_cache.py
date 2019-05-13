import intervaltree
import util
import numpy as np
import pandas as pd
import datetime
import pprint


OFFSET = datetime.timedelta(minutes=1)


class IntervalData:

    def __init__(self, resolution, start_time, end_time, dataframe):
        self.resolution = resolution
        self.start_time = start_time
        self.end_time = end_time
        self.dataframe = dataframe

    def __eq__(self, other):
        return (self.resolution == other.resolution
                and self.start_time == other.start_time
                and self.end_time == other.end_time)


    def __repr__(self):
        return f'''
        IntervalData(
        {self.resolution},
        '{self.start_time}',
        '{self.end_time}',

        {self.dataframe.describe()})'''


class ChartCache(intervaltree.IntervalTree):
    '''
    1) (Find ones needed to be udpated)
    Given start, end time and resolution, find all intevals that either
    don't exist in cache or exist in cache but of lower resolution than
    resolution
    2) Merge new data in; keep the highest resolution
    '''

    def split_overlaps(self):
        """Overridden library's implementation, to slice every boundry instead.
        ====================Original=========================
        Finds all intervals with overlapping ranges and splits them
        along the range boundaries.

        Completes in worst-case O(n^2*log n) time (many interval
        boundaries are inside many intervals), best-case O(n*log n)
        time (small number of overlaps << n per interval).
        ====================End Original=========================
        """
        if not self:
            return
        if len(self.boundary_table) == 2:
            return

        bounds = sorted(self.boundary_table)  # get bound locations

        for lbound, ubound in zip(bounds[:-1], bounds[1:]):
            self.slice(lbound)
            self.slice(ubound)

    def slice(self, point, datafunc=None):
        """Overridden library's implementation, to call custom splitter when datafunc is not
        provided.
        ======================Original=============================
        Split Intervals that overlap point into two new Intervals. if
        specified, uses datafunc(interval, islower=True/False) to
        set the data field of the new Intervals.
        :param point: where to slice
        :param datafunc(interval, isupper): callable returning a new
        value for the interval's data field
        ======================End Original=============================
        """
        hitlist = set(iv for iv in self.at(point) if iv.begin < point)
        insertions = set()
        if datafunc:
            for iv in hitlist:
                insertions.add(intervaltree.Interval(iv.begin, point, datafunc(iv, True)))
                insertions.add(intervaltree.Interval(point, iv.end, datafunc(iv, False)))
        else:
            for iv in hitlist:
                insertions.add(
                    intervaltree.Interval(iv.begin, point,
                    util.period_data_splitter(iv, True, point)))
                insertions.add(
                    intervaltree.Interval(point, iv.end,
                    util.period_data_splitter(iv, False, point)))
        self.difference_update(hitlist)
        self.update(insertions)

    def merge(self, start_time, end_time, data_resolution, data):
        '''Given the start_time, end_time and the resolution of a list, merges into the cache
        '''
        # test left and right side of new_period to see if we can merge with
        # adjacent periods, only merge if resolutions were the same
        new_period = util.list_tointerval(start_time, end_time, data_resolution, data)
        self.add(new_period)
        self.split_overlaps()
        self.merge_equals(data_reducer=util.period_data_reducer)
        overlapped_periods = sorted(self[new_period.begin-OFFSET:new_period.end+OFFSET])
        for i in range(1, len(overlapped_periods)):
            if overlapped_periods[i].data.resolution == overlapped_periods[
                    i - 1].data.resolution:
                self.add(
                    intervaltree.Interval(overlapped_periods[i].begin - OFFSET,
                    overlapped_periods[i].end,
                             overlapped_periods[i].data))
                self.remove(overlapped_periods[i])
        self.merge_overlaps(data_reducer=util.period_data_combinator)

    def get(self, start_time, end_time, data_resolution=0):
        ''' Give start_time and end_time (exclusive), guranteed being completely envelopped by
        some intervals in the cache, return data unalterd from cache
        if data is data_resolution. Otherwise, return the rolled up or extrapolated.
        '''
        if isinstance(start_time, int):
            start_time = util.time_stamp(start_time)
        if isinstance(end_time, int):
            end_time = util.time_stamp(end_time)

        # overlapping ones; the end time in period is exclusive
        periods = sorted(self[start_time:end_time])

        if data_resolution:
            dfs = []
            for p in periods:
                if p.data.resolution < data_resolution:
                    dfs.append(
                        p.data.dataframe.groupby(pd.Grouper(freq=f'{data_resolution}S')).mean()
                    )
                elif p.data.resolution > data_resolution:
                    period_resolution = p.data.resolution
                    period_start_time = p.begin
                    period_end_time = p.end
                    # portion of of what we wanted
                    if period_end_time == end_time:
                        datalst = p.data.dataframe[start_time:end_time]['temperature'].tolist()
                    else:
                        datalst = p.data.dataframe[start_time:end_time][:-1]['temperature'].tolist()
                    extrapolated_data = util.extrapolated_data(
                        datalst, int(np.ceil(period_resolution/data_resolution)))
                    dates_for_extrapolated = pd.date_range(
                        max(period_start_time, start_time),
                        min(period_end_time, end_time),
                        freq=f'{data_resolution}S'
                    )[:-1]
                    extrapolated_df = pd.DataFrame(
                        extrapolated_data,
                        index=dates_for_extrapolated,
                        columns=['temperature']
                    )
                    dfs.append(extrapolated_df)
                else:
                    dfs.append(p.data.dataframe)
        else:
            dfs = [p.data.dataframe for p in periods]

        df = pd.concat(dfs)
        # periods might contain more data than we need, dataframe indexing includes end index, so
        # we need to remove 1 extra data point should periods has more data than we need.
        if df.index.max() > end_time:
            data = df[start_time:end_time][:-1]['temperature']
        else:
            data = df[start_time:end_time]['temperature']

        return data.values.tolist()


    def intervals_be_updated(self, new_start_time, new_end_time, new_resolution):
        ''' Provided either start times are equal or end times are equal, return the
        list of (start_time, end_time, resolution) that we need to request data from backend for
        , intervals that need to be reuqested and crossing the boundries of the cache periods
        might get chopped into 2 parts (refactor:)
        '''
        if isinstance(new_start_time, int):
            new_start_time = util.time_stamp(new_start_time)
        if isinstance(new_end_time, int):
            new_end_time = util.time_stamp(new_end_time)

        if not self[new_start_time:new_end_time]:
            return [(util.epoch(new_start_time), util.epoch(new_end_time), new_resolution)]

        # update on the existing cache
        overlapped = sorted(self[new_start_time:new_end_time])
        existing_be_updated = [
                (max(p.begin, new_start_time), min(p.end, new_end_time), new_resolution)
                for p in overlapped
                if p.data.resolution > new_resolution
            ]

        # currently unfilled
        start_end_times = [(p.begin, p.end) for p in overlapped]
        overlapped_start_time = min(start_end_times, key=lambda t: t[0])[0]
        overlapped_end_time = max(start_end_times, key=lambda t: t[1])[1]
        if new_start_time < overlapped_start_time:
            non_existing_be_updated_start_time = [(new_start_time, overlapped_start_time, new_resolution)]
        else:
            non_existing_be_updated_start_time = []
        if new_end_time > overlapped_end_time:
            non_existing_be_updated_end_time = [(overlapped_end_time, new_end_time, new_resolution)]
        else:
            non_existing_be_updated_end_time = []

        result = existing_be_updated + non_existing_be_updated_end_time + non_existing_be_updated_start_time
        result_epoch_time = [
            (util.epoch(start_time), util.epoch(end_time), resolution)
            for start_time, end_time, resolution in result
        ]

        return result_epoch_time


    def __repr__(self):
        return pprint.pformat(sorted(self), indent=4)


