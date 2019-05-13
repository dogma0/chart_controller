import logging
import chart_cache as cc
import util


logging.basicConfig(level=logging.DEBUG)


class Controller:
    '''All time units are in epoch time in this class, everything else in this package uses
    pd.TimeStamp unless otherwise stated in the code
    '''

    @staticmethod
    async def create(ui, backend, start_time, end_time, cache=None):
        '''Initializes your object with the starting chart range. You should perform
        any service calls needed to render the chart as quickly as possible. The
        startTime and endTime are guaranteed to be aligned with the chart period;
        i.e. if the chart covers a four week span, startTime and endTime will be
        aligned on hourly boundaries; if the chart covers a 36 minute span,
        startTime and endTime will be aligned on one-minute boundaries.

        startTime - The first datapoint to be rendered, inclusive, in
        seconds since the epoch.
        endTime - The last datapoint to be rendered, exclusive, in seconds
        since the epoch.

        The async keyword doesn't work with magic methods, e.g. __init__, hence this method
        '''
        self = Controller()
        self.ui = ui
        self.backend = backend
        # maps (start_time, end_time, resolution) -> task_id
        self._backend_reqs = {}
        # maps task_id -> (start_time, end_time, resolution)
        self._ui_reqs = {}
        # id for the last started task
        self._cur_tid = 0
        self._start_time = start_time
        self._end_time = end_time
        self._cache = cc.ChartCache() if not cache else cache

        self.respond_ui(
            [None] * util.num_datapoints(end_time - start_time), start_time, end_time
        )
        self.init_metadata(start_time, end_time)
        await self.request_data(start_time, end_time)

        self._cur_tid += 1
        return self

    def init_metadata(self, start_time, end_time):
        # keeping track what we've rendered
        # useful for ensuring UI sees the most up-to-date rendering
        self._backend_reqs[
            (start_time, end_time, util.resolution(end_time - start_time))] = self.cur_tid
        self.ui_reqs[self.cur_tid] = (
            start_time,
            end_time,
            util.resolution(end_time-start_time))


    def respond_ui(self, data, ui_req_start_time, ui_req_end_time):
        self.record_ui_req(self.cur_tid,
                           (ui_req_start_time,
                            ui_req_end_time,
                            util.resolution(ui_req_end_time - ui_req_start_time)))
        self.ui.set_chart_data(data)

    async def request_data(self, start_time, end_time, data_resolution=None):
        if not data_resolution:
            data_resolution = util.resolution(end_time - start_time)
        self.record_backend_req((start_time, end_time, data_resolution), self.cur_tid)
        await self.backend.request_temperature_data(
            start_time, end_time, data_resolution
        )

    def record_ui_req(self, tid, start_end_time_resolution_tup):
        self.ui_reqs[tid] = start_end_time_resolution_tup


    def record_backend_req(self, start_end_time_resolution, tid):
        self.backend_reqs[start_end_time_resolution] = tid

    def ui_req_times_and_resolution(self, tid):
        return self.ui_reqs[tid]

    def backend_req_tid(self, start_end_time_resolution):
        return self.backend_reqs[start_end_time_resolution]

    def data_fromcache(self, start_time, end_time, at_resolution):
        return self.cache.get(
            start_time, end_time, at_resolution
        )

    @property
    def cur_tid(self):
        return self._cur_tid

    @cur_tid.setter
    def cur_tid(self, v):
        self._cur_tid = v

    @property
    def ui_reqs(self):
        return self._ui_reqs

    @ui_reqs.setter
    def ui_reqs(self, v):
        self._ui_reqs = v

    @property
    def backend_reqs(self):
        return self._backend_reqs

    @backend_reqs.setter
    def backend_reqs(self, v):
        self._backend_reqs = v

    @property
    def cache(self):
        return self._cache

    @cache.setter
    def cache(self, new_cache):
        self._cache = new_cache

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    def start_time(self, new_start_time):
        self._start_time = new_start_time

    @property
    def end_time(self):
        return self._end_time

    @end_time.setter
    def end_time(self, new_end_time):
        self._end_time = new_end_time

    async def set_start_time(self, new_start_time):
        if self.start_time == new_start_time:
            return
        new_resolution = util.resolution(abs(new_start_time - self.end_time))
        intervals_be_updated = self.cache.intervals_be_updated(
            new_start_time, self.end_time, new_resolution
        )

        if not intervals_be_updated:
            self.respond_ui(
                self.cache.get(new_start_time, self.end_time), new_start_time, self.end_time
            )
        else:
            filler = [None] * util.num_datapoints(
                max(self.start_time - new_start_time, 0), data_resolution=new_resolution)
            from_cache = self.data_fromcache(
                max(self.start_time, new_start_time),
                self.end_time,
                new_resolution
            )
            be_rendered = filler + from_cache
            self.respond_ui(be_rendered, new_start_time, self.end_time)
            for req_start_time, req_end_time, _ in intervals_be_updated:
                await self.request_data(req_start_time, req_end_time, new_resolution)

        self.start_time = new_start_time
        # increment id for the next set request from ui
        self.cur_tid += 1


    async def set_end_time(self, new_end_time):
        if self.end_time == new_end_time:
            return
        new_resolution = util.resolution(abs(new_end_time - self.start_time))
        intervals_be_updated = self.cache.intervals_be_updated(
            self.start_time, new_end_time, new_resolution
        )

        if not intervals_be_updated:
            self.respond_ui(
                self.cache.get(self.start_time, new_end_time), self.start_time, new_end_time
            )
        else:
            filler = [None] * util.num_datapoints(
                max(new_end_time - self.end_time, 0), data_resolution=new_resolution)
            from_cache = self.data_fromcache(
                self.start_time, min(self.end_time, new_end_time), new_resolution
            )
            be_rendered = from_cache + filler
            self.respond_ui(be_rendered, self.start_time, new_end_time)
            for req_start_time, req_end_time, _ in intervals_be_updated:
                await self.request_data(
                    req_start_time, req_end_time, data_resolution=new_resolution)

        self.end_time = new_end_time
        # increment id for the next set request from ui
        self.cur_tid += 1


    def receive_temperature_data(self, start_time, end_time, data_resolution, data):
        '''Merge new data into cache and trigger a rendering if it doesn't negatively
        affect user experience'''
        data_task_id = self.backend_req_tid((start_time, end_time, data_resolution))

        # Only render when the data we are receiving is for a task (thus a set request from UI)
        # that we have not finished renderings for. Otherwise, only record the data
        self.cache.merge(start_time, end_time, data_resolution, data)
        if self.cur_tid <= data_task_id + 1:
            req_start_time, req_end_time, req_resolution =\
                self.ui_req_times_and_resolution(data_task_id)
            be_rendered = self.cache.get(req_start_time, req_end_time, req_resolution)
            self.respond_ui(be_rendered, req_start_time, req_end_time)
        else:
            logging.debug('''receive_temperature_data: absorbing data but not rendering''')

