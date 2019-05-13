import pytest
import util
import numpy as np
import pandas as pd
import intervaltree
import chart_cache as cc
import backend as backend_mod
import ui as ui_mod
import controller as controller_mod


np.random.seed(0)

# ======================================= Chart Cache=================================


def temperature_data_lst(length):
    return np.floor(np.random.randn(length) * 2.5 + 20).tolist()

dates = pd.date_range(
    '2000-01-01 00:00:00',
    '2000-03-01 11:59:00',
    freq=pd.offsets.Minute(1)
)
length = len(dates)

data_jan1st0000_to_mar1st1159 = pd.DataFrame(
        temperature_data_lst(length),
        index=dates,
        columns=['temperature']
    )

def rolled_up(df, start_time, end_time, resolution):
    ''' the rolled up version of the data in df, from start time to end time (exclusive)
    '''
    # df has the end time as end_time, then no need to take out the last row
    if df.index[-1] == end_time:
        data_in_interval = df[start_time:end_time]
    else:
        data_in_interval = df[start_time:end_time][:-1]
    return data_in_interval.groupby(pd.Grouper(freq=f'{resolution}S')).mean()


def state_0am_to_10am():
    '''
    '''
    am_0 = util.time_stamp('2000-01-01 00:00:00')
    am_10 = util.time_stamp('2000-01-01 10:00:00')
    data = rolled_up(data_jan1st0000_to_mar1st1159, am_0, am_10, 300)
    t = cc.ChartCache()
    t.add(
        intervaltree.Interval(
            am_0,
            am_10,
            cc.IntervalData(
                300,
                am_0,
                am_10,
                data
            )
        )
    )
    return (am_0, am_10, t)

def state_1am_to_1am_plus_1mo():
    am_1 = util.time_stamp('2000-01-01 01:00:00')
    am_1_plus_1mo = util.time_stamp('2000-02-01 01:00:00')
    t = cc.ChartCache()
    t.add(
        intervaltree.Interval(
            am_1,
            am_1_plus_1mo,
            cc.IntervalData(
                3600,
                am_1,
                am_1_plus_1mo,
                rolled_up(data_jan1st0000_to_mar1st1159, am_1, am_1_plus_1mo, 3600)
            )
        )
    )
    return (am_1, am_1_plus_1mo, t)

@pytest.fixture
def data_jan1st0000_to_mar1st1159_fixture():
    return data_jan1st0000_to_mar1st1159

@pytest.fixture
def state_0am_10am_fixture(data_jan1st0000_to_mar1st1159_fixture):
    return state_0am_to_10am()

@pytest.fixture
def state_1am_to_1am_plus_1mo_fixture():
    return state_1am_to_1am_plus_1mo()


def test_slice(data_jan1st0000_to_mar1st1159_fixture, state_0am_10am_fixture):
    am_5 = util.time_stamp('2000-01-01 05:00:00')
    am_0, am_10, cache = state_0am_10am_fixture

    cache.slice(am_5)
    periods = sorted(cache)
    # assert there exists 2 intervals
    assert len(periods) == 2

    # assert start and end times for the 2 intervals
    first = periods[0]
    second = periods[1]
    assert first.begin == am_0
    assert first.end == am_5
    assert second.begin == am_5
    assert second.end == am_10

def test_intervals_be_updated_1_interval(state_0am_10am_fixture):
    _, _, cache = state_0am_10am_fixture
    intervals_be_updated = cache.intervals_be_updated(
        util.time_stamp('2000-01-01 10:00:00'), util.time_stamp('2000-01-01 12:00:00'), 300
    )
    assert len(intervals_be_updated) == 1
    assert intervals_be_updated[0] == (
        util.epoch('2000-01-01 10:00:00'),
        util.epoch('2000-01-01 12:00:00'),
        300
    )

def test_intervals_be_updated_1_interval_partial_interval_inbetween(state_0am_10am_fixture):
    '''5am to 6am needs to be updated in the existing 0am to 10am
    '''
    _, _, cache = state_0am_10am_fixture
    am_5 = util.time_stamp('2000-01-01 05:00:00')
    am_6 = util.time_stamp('2000-01-01 06:00:00')
    intervals_be_updated = cache.intervals_be_updated(
        am_5, am_6, 60
    )
    assert len(intervals_be_updated) == 1
    assert intervals_be_updated[0] == (
        util.epoch(am_5),
        util.epoch(am_6),
        60
    )


def test_intervals_be_updated_1_interval_partial_interval_edging(state_0am_10am_fixture):
    '''9am to 10am needs to be updated in the existing 0am to 10am
    '''
    _, _, cache = state_0am_10am_fixture
    am_9 = util.time_stamp('2000-01-01 09:00:00')
    am_10 = util.time_stamp('2000-01-01 10:00:00')
    intervals_be_updated = cache.intervals_be_updated(
        am_9, am_10, 60
    )
    assert len(intervals_be_updated) == 1
    assert intervals_be_updated[0] == (
        util.epoch(am_9),
        util.epoch(am_10),
        60
    )

def test_intervals_be_updated_2_intervals_overextend(state_0am_10am_fixture):
    '''9am to 11:30am needs to be updated in the existing 0am to 10am
    '''
    _, _, cache = state_0am_10am_fixture
    am_9 = util.time_stamp('2000-01-01 09:00:00')
    am_1130 = util.time_stamp('2000-01-01 11:30:00')
    am_10 = util.time_stamp('2000-01-01 10:00:00')
    intervals_be_updated = cache.intervals_be_updated(
        am_9, am_1130, 60
    )

    assert len(intervals_be_updated) == 2
    assert intervals_be_updated[0] == (
        util.epoch(am_9),
        util.epoch(am_10),
        60
    )
    assert intervals_be_updated[1] == (
        util.epoch(am_10),
        util.epoch(am_1130),
        60
    )

def test_intervals_be_updated_3_intervals(
        state_1am_to_1am_plus_1mo_fixture, data_jan1st0000_to_mar1st1159_fixture):
    '''Scenario where the cache is segmented into
    (3600, 60, 3600, 60, 3600) segments within a 1 hour period, so when we set endtime
    so that resolution changes to 60 or 300 seconds, we would need to request for 3 segmentd intervals
    '''
    am_1, am_1am_plus_1mo, cache = state_1am_to_1am_plus_1mo_fixture
    # segmented as below
    # (9:00, 9:05) -> 3600, (9:05, 9:10)->60, (9:10,9:15)->3600, (9:15,9:20)->60, (9:20,9:20+1mo)->3600
    # intervals_be_updated(9:00, 10:00, 60 or 300) would lead to intervals with 3600 needing to be updated

    def date_template(minutes):
        return f'''2000-01-01 09:{minutes}'''
    am_9 = util.time_stamp(date_template('00'))
    am_905 = util.time_stamp(date_template('05'))
    am_910 = util.time_stamp(date_template('10'))
    am_915 = util.time_stamp(date_template('15'))
    am_920 = util.time_stamp(date_template('20'))
    am_10 = util.time_stamp('2000-01-01 10:00:00')
    am_1055 = util.time_stamp('2000-01-01 10:55:00')
    am_920_plus_1mo = util.time_stamp('2000-02-01 09:20:00')

    # Write to (9:05, 9:10) and (9:15, 9:20)
    cache.merge(am_905, am_910, 60, temperature_data_lst(5))
    cache.merge(am_915, am_920, 60, temperature_data_lst(5))

    expected_intervals = [(util.epoch(st), util.epoch(et), 60)
                                    for st, et in
                                    [
                                        (am_9, am_905),
                                        (am_910, am_915),
                                        (am_920, am_1055),
                                    ]]
    intervals_be_updated = cache.intervals_be_updated(
        util.epoch(am_9),
        util.epoch(am_1055),
        60
    )

    assert len(intervals_be_updated) == 3
    assert intervals_be_updated == expected_intervals



def test_get(state_0am_10am_fixture):
    am_0, am_10, cache = state_0am_10am_fixture
    am_8 = util.time_stamp('2000-01-01 08:00:00')
    get_result = cache.get(am_0, am_10, 300)
    assert len(get_result) == 120
    assert get_result == sorted(cache)[0].data.dataframe[am_0:am_10]['temperature'].tolist()

    get_result1 = cache.get(am_8, am_10, 300)
    assert len(get_result1) == 24
    assert get_result1 == sorted(cache)[0].data.dataframe[am_8:am_10]['temperature'].tolist()


def test_merge(data_jan1st0000_to_mar1st1159_fixture, state_0am_10am_fixture):
    am_0, am_10, cache = state_0am_10am_fixture
    am_11 = util.time_stamp('2000-01-01 11:00:00')
    new_data = temperature_data_lst(60)
    cache.merge(am_10, am_11, 60, new_data)
    cache_state = cache.get(am_10, am_11)
    assert len(cache_state) == 60
    assert cache_state == new_data

# ======================================= End Chart Cache=================================

# ====================================== Controller ======================================
@pytest.mark.asyncio
async def test_empty_cache_1pm_to_2pm():
    backend = backend_mod.MockBackend()
    ui = ui_mod.MockUI()

    # Jan 1st, 2000 1pm GMT
    start_time = util.epoch('2000-01-01 13:00:00')
    # Jan 1st, 2000 2pm GMT
    end_time = util.epoch('2000-01-01 14:00:00')

    expected_resolution = 60
    expected_num_datapoints = 60

    # init the controller and trigger request_temperature_data and set_chart_data
    controller = await controller_mod.Controller.create(ui, backend, start_time, end_time)

    # assert the immediate set_chart_data called with all Nones by controller to UI
    assert [None] * expected_num_datapoints == ui.datapoints

    # assert controller asks backend for all the data
    assert backend.last_request == (start_time, end_time, expected_resolution)

    # mimics backend calling controller's receive_temperature_data
    expected_data = temperature_data_lst(expected_num_datapoints)
    controller.receive_temperature_data(
        start_time,
        end_time,
        expected_resolution,
        expected_data
    )

    # assert controller renders the recevied data correctly
    assert expected_data == ui.datapoints

    # To make this a test fixture
    return (backend, ui, controller)


@pytest.fixture
async def state_with_1pm_to_2pm_fixture():
    return await test_empty_cache_1pm_to_2pm()


@pytest.mark.asyncio
async def test_set_end_time_with_cache_being_partial_and_same_resolution(
        state_with_1pm_to_2pm_fixture):
    backend, ui, controller = state_with_1pm_to_2pm_fixture
    rendered_data = ui.datapoints[:]

    # half an hour later than original end time
    old_end_time = controller.end_time
    new_end_time = util.epoch('2000-01-01 14:30:00')

    # assert first render renders the correct data to UI
    await controller.set_end_time(new_end_time)
    assert controller.end_time == new_end_time
    assert rendered_data + [None] * 30  == ui.datapoints

    # assert backend's received for the right request
    assert (
        util.epoch('2000-01-01 14:00:00'),
        util.epoch('2000-01-01 14:30:00'),
        60
    ) == backend.last_request


    # assert second render renders correctly after the data comes back from backend
    data_received_from_backend = temperature_data_lst(30)
    controller.receive_temperature_data(
        old_end_time, new_end_time, 60, data_received_from_backend
    )

    assert rendered_data + data_received_from_backend == ui.datapoints

@pytest.mark.asyncio
async def test_set_end_time_with_cache_being_partial_rolled_up(
        state_with_1pm_to_2pm_fixture):
    backend, ui, controller = state_with_1pm_to_2pm_fixture
    rendered_data = ui.datapoints[:]
    old_end_time = controller.end_time
    new_end_time = util.epoch(util.time_stamp('2000-01-01 17:00:00'))

    # First render
    await controller.set_end_time(new_end_time)
    assert util.scaled_data(rendered_data, 60, 300) + [None] * 36 == ui.datapoints

    # backend receives a request for data
    assert (
        util.epoch('2000-01-01 14:00:00'),
        util.epoch('2000-01-01 17:00:00'),
        300
    ) == backend.last_request

    # Second render
    data_from_backend = temperature_data_lst(36)
    # ??
    controller.receive_temperature_data(
        old_end_time, new_end_time, 300, data_from_backend)
    assert ui.datapoints ==  util.scaled_data(rendered_data, 60, 300) + data_from_backend

@pytest.mark.asyncio
async def test_set_end_time_with_cache_being_partial_extrapolate(
        state_1am_to_1am_plus_1mo_fixture):
    am_1, am_1_plus_1mo, cache = state_1am_to_1am_plus_1mo_fixture
    backend = backend_mod.MockBackend()
    ui = ui_mod.MockUI()
    controller = await controller_mod.Controller.create(
        ui,
        backend,
        util.epoch(am_1),
        util.epoch(am_1_plus_1mo),
        cache)
    am_3 = util.time_stamp('2000-01-01 03:00:00')

    # First render
    await controller.set_end_time(util.epoch(am_3))
    assert util.extrapolated_data(
        sorted(cache)[0].data.dataframe[am_1: am_3]['temperature'][:-1].tolist(),
        12
    ) == ui.datapoints

    # backend recevies request for 1 to 3am
    assert backend.last_request == (
        util.epoch(am_1),
        util.epoch(am_3),
        300
    )

    # renders for 1 to 3am
    data_from_backend = temperature_data_lst(24)
    controller.receive_temperature_data(
        util.epoch(am_1), util.epoch(am_3), 300, data_from_backend
    )
    assert ui.datapoints == data_from_backend


@pytest.mark.asyncio
async def test_same_endtime_nonempty_cache(state_with_1pm_to_2pm_fixture):
    '''Set end time to the exact same tiem as before, should not trigger any state changes
    '''
    backend, ui, controller = state_with_1pm_to_2pm_fixture
    end_time = controller.end_time

    # No render
    ui_last_mod = ui.last_mod
    # No request to backend
    backend_last_mod = backend.last_mod
    await controller.set_end_time(end_time)
    assert ui_last_mod == ui.last_mod
    assert backend_last_mod == backend.last_mod

@pytest.mark.asyncio
async def test_set_endtimie_twice_out_of_order_recev(state_1am_to_1am_plus_1mo_fixture):
    '''ui makes 2 set requests to controller, data for set request #2 comes backend
    earlier than #1, controller renders the data for set requset #2 but not #1, and
    it caches both
    '''
    am_1, am_1_plus_1mo, cache = state_1am_to_1am_plus_1mo_fixture
    backend = backend_mod.MockBackend()
    ui = ui_mod.MockUI()
    controller = await controller_mod.Controller.create(
        ui,
        backend,
        util.epoch(am_1),
        util.epoch(am_1_plus_1mo),
        cache)
    # next task id wil be
    assert controller.cur_tid == 1

    # set request #1: (1am, 2am)
    am_2 = util.time_stamp('''2000-01-01 02:00:00''')
    await controller.set_end_time(util.epoch(am_2))
    assert backend.last_request == (
        util.epoch(am_1),
        util.epoch(am_2),
        60
    )
    # next task id wil be
    assert controller.cur_tid == 2

    # set request #2: (1am, 3am)
    am_3 = util.time_stamp('''2000-01-01 03:00:00''')
    await controller.set_end_time(util.epoch(am_3))
    assert backend.last_request == (
        util.epoch(am_1),
        util.epoch(am_3),
        300
    )
    # next task id wil be
    assert controller.cur_tid == 3

    # recevies data for the 2nd request
    data_2nd_req = temperature_data_lst(24)
    controller.receive_temperature_data(
        util.epoch(am_1), util.epoch(am_3), 300, data_2nd_req
    )
    # renders for 2nd request
    assert ui.datapoints == data_2nd_req

    ui_mod_time_before_recv = ui.last_mod
    data_1st_req = temperature_data_lst(60)
    controller.receive_temperature_data(
        util.epoch(am_1), util.epoch(am_2), 60, data_1st_req
    )
    # no render triggered by this receipt
    assert ui.datapoints == data_2nd_req and ui_mod_time_before_recv == ui.last_mod
    backend_mod_before = backend.last_mod
    assert len(controller.cache.get(
        am_1, am_3, 300
    )) == 24
    # didn't go to backend for these data
    assert backend.last_mod == backend_mod_before


# ====================================== End Controller ==============================

# =========================================== UTIL =====================================

def test_scaled_data_rolls_up():
    temperatures = [20, 21, 22, 23, 24, 25, 26]
    old_resolution, new_resolution = 60, 300
    assert [22, 25.5] == util.scaled_data(temperatures, old_resolution,
                                           new_resolution)

def test_scaled_data_extrapolates():
    temperatures = [20, 21]
    old_resolution, new_resolution = 300, 60
    assert [20, 20, 20, 20, 20, 21, 21, 21, 21,
            21] == util.scaled_data(temperatures, old_resolution,
                                     new_resolution)


def test_scaled_data_stays_the_same():
    # same resolution
    temperatures = [20, 21, 22]
    old_resolution, new_resolution = 300, 300
    assert temperatures == util.scaled_data(temperatures,
                                              old_resolution,
                                              new_resolution)


def test_scaled_data_throws_when_invalid_resolution():
    # throw an exception when one of the resolutions is not 1 min, 5 min or 1 hour
    temperatures = [20, 21, 22]
    old_resolution, wrong_new_resolution1 = 300, 301
    with pytest.raises(ValueError):
        util.scaled_data(temperatures, old_resolution, wrong_new_resolution1)
    old_resolution, wrong_new_resolution2 = 0, 300
    with pytest.raises(ValueError):
        util.scaled_data(temperatures, old_resolution, wrong_new_resolution2)

# ==========================================END UTIL ======================================

# ================================ DEMO ==========================================
@pytest.mark.asyncio
async def test_demo():

    # let's get our testing environments set up

    # a backend instance acting that would take in our request for data and sends us back data

    backend = backend_mod.MockBackend()

    # a ui instance that would take in our rendering request

    ui = ui_mod.MockUI()

    # let's set up the initial start and end time for the controller

    start_time = util.epoch('2000-01-01 13:00:00')
    end_time = util.epoch('2000-01-01 14:00:00')

    # example 1) Empty Cache: Controller is able to respond immediately with Nones and render when backend sends back data

    # instantiate our controller
    controller = await controller_mod.Controller.create(ui, backend, start_time, end_time)

    # there was our immediate reponse to the UI in the logs

    # that instantiation also initated a request of 60 datapoints for 13:00 to 14:00 to the backend, we can check our backend instance

    # the start time, end time (epoch time) and the resolution of the request the controller last sent to the backend
    backend.last_request

    util.time_stamp(backend.last_request[0]), util.time_stamp(backend.last_request[1])

    # this is to mimic the backend sending back the data

    data_to_sendback = temperature_data_lst(60)

    data_to_sendback

    len(data_to_sendback)

    # let's send the data to controller

    controller.receive_temperature_data(
        start_time,
        end_time,
        60,
        data_to_sendback
    )

    # this controller immediately renders the data we just sent back

    # End of example 1


    # example 2) parital cache, no change in resolution: Controller is able to respond immediately with the data in cache for the part that it stored, then later request the data that it does not have, and render the data it receivs from the backend when backend sends the data

    # let's set the end time to a new one; note this new end doesn't change the resolution

    # old: 14:00, new: 14:30

    new_end_time = util.epoch('2000-01-01 14:30:00')

    await controller.set_end_time(new_end_time)

    # first 60 data points are the same as what we rendered before changing the end time, this shows the controller it's able to use the data in the cache. In addition, it renders 30 Nones for the data it's yet received

    # these are to check what was just rendered to ui
    len(ui.datapoints)

    ui.datapoints[:59]

    ui.datapoints[60:]

    # let's check that our backend does receive the controller's request for data
    backend.last_request

    util.time_stamp(backend.last_request[0]), util.time_stamp(backend.last_request[1])

    # the backend sends the controller the data it requested

    data_to_sendback = temperature_data_lst(30)

    controller.receive_temperature_data(
        end_time,
        new_end_time,
        60,
        data_to_sendback
    )

    # controller renders the data it's just received alongside the data it's in cache

    # End of example 2

    # example 3) Changing Resolution: Upon a set or end time change, and this change changes the resolution rendered to UI, controller is able to respond immediately with "rolled up" or "extrapolated" verion of the data it has in cache, request data for data it doesn't yet store in cache or it only has the lower than satisfactory resolution (e.g. UI's sets controller's end time such that resolution is now 1 minute, but the controller only has data in 1 hour resolution)

    # let's set the end time from 14:30 to 15:00. Now the start time and end time is from 13:00 to 15:00. We must change the resolution in our request to rendering to 5 minutes according to the rules.

    new_end_time2 = util.epoch('2000-01-01 15:00:00')

    await controller.set_end_time(new_end_time2)

    # controller renders 24 data points for 24 5-minute chunks in 13:00 to 15:00

    # the number, 20.4, our first value in the rendering, is the average of 13:00 to 13:04. This shows, in the controller's immediate response to the UI, it returns the "rolled up" version of the data it already has in cache.

    # We can verify 20.4 is indeed the average of the 5 values in the previous rendering.

    # the values were [22.0, 18.0, 23.0, 23.0, 16.0]
    import statistics as stats
    stats.mean([22.0, 18.0, 23.0, 23.0, 16.0])

    # let's take a look at the backend

    # let's check our backend to make sure we've only requested data for 14:30 to 15:00 since we already have data for 13:00 to 14:30

    backend.last_request

    util.time_stamp(backend.last_request[0]), util.time_stamp(backend.last_request[1])

    # this shows the controller does indeed only request data from the backend that it doesn't already have in cache

    # end of example 3


    # ========================================================================================================
    # The following examples are to show some of features that weren't described in the spec, but implemented

    # Example 4) Caches Everything Old and New: in a situation, where UI changes resolution back and forth, the controller caches both the new data it recevies and old data. For the same time period, controller always caches the highest resolution version (i.e. 1 min is of the highest version)

    # e.g. In our previous example, UI's resolution's now in 5 minutes, i.e. 13:00 to 15:00. If we change back to 14:30, controller will be able to use the data it's cached from the past to fulfill the request



    # 14:30
    util.time_stamp(new_end_time)

    await controller.set_end_time(new_end_time)


    # We didn't use request any data from the backend
    util.time_stamp(backend.last_request[0]), util.time_stamp(backend.last_request[1])

    # End of example 4


    # example 5) Able to request data for multiple seperated and small time intervals, no wasteful requests to backend

    # Here we will define a new cache

    # this cache has hourly data starting from 2000-01-01 01:00 to 2000-02-01 01:00
    am_1, am_1am_plus_1mo, cache = state_1am_to_1am_plus_1mo()

    # defining more time stamps

    def date_template(minutes):
        return f'''2000-01-01 09:{minutes}'''
    am_9 = util.time_stamp(date_template('00'))
    am_905 = util.time_stamp(date_template('05'))
    am_910 = util.time_stamp(date_template('10'))
    am_915 = util.time_stamp(date_template('15'))
    am_920 = util.time_stamp(date_template('20'))
    am_10 = util.time_stamp('2000-01-01 10:00:00')
    am_1055 = util.time_stamp('2000-01-01 10:55:00')

    # The important thing to observe here is (1am, 1am + 1month), i.e. 2000-01-01 01:00 to 2000-02-01 01:00, is entirely in 3600 (hourly) resolution

    # Let's write some higher resolution data into the cache to to make cache fragmented into different resolutions
    cache.merge(am_905, am_910, 60, temperature_data_lst(5))
    cache.merge(am_915, am_920, 60, temperature_data_lst(5))

    # So the cache now looks like this:

    # (9:00, 9:05) in 3600s (hourly) resolution, (9:05, 9:10) in 60, (9:10,9:15) in 3600, (9:15,9:20) in 60, (9:20,9:20+1month) in 3600; the bottom line is the cache is now fragmented

    # As mentioned before, the cache aggresively stores the highest resolution of the data it's ever seen for every time interval.

    # The thing to observe here is the cache only request data that it actually needs
    # so (9:00, 9:05), (9:10, 9:15), (9:20, 10:55) will be requested

    intervals_be_updated = cache.intervals_be_updated(
        util.epoch(am_9),
        util.epoch(am_1055),
        60
    )

    [(util.time_stamp(x[0]), util.time_stamp(x[1])) for x in intervals_be_updated]

    # End example 5

    # Example 6) Consistent Rendering: In a situation where backend sends back data in a different order than we'd requested, controller makes sure the UI only sees the most up-to-date state. An alterantive naive approch would lead to user to see a "lagging" effect

    # As mentioned in the spec, the data backend sends back can come in a different order than the order we requested

    # As an example:

    # Assume UI sets controller's end time, let's call this set_end_time call set_end_time#A.

    # The controller immediately respond with what it can and request data from backend if needed, just like how we described above.

    # Now assume UI makes another call, set_end_time#B. Some amount of time later, assume the data for which gets back from the backend to controller before the data for set_end_time#A does, which is a different order than how we'd requested to the backend.

    # Controller renders the data for set_end_time#B to UI, but when the data set_end_time#A comes back, it doesn't render to UI and only stores the data in its cache.

    # The reason for this is, if we had rendered for the data for set_end_time#A, from the user perspective, it would seem like the system jump back to the previous state and makes the system seem slow.

    # Let's see all of it in action.

    # setting the controller and the mock instances
    am_1, am_1_plus_1mo, cache = state_1am_to_1am_plus_1mo()
    backend = backend_mod.MockBackend()
    ui = ui_mod.MockUI()
    controller = await controller_mod.Controller.create(
        ui,
        backend,
        util.epoch(am_1),
        util.epoch(am_1_plus_1mo),
        cache)

    # We can ignore the data it logged here; it's not important

    # Current start time: 1am, end time: 1am + 1 month

    # set end time request #A: (1am, 2am)
    am_2 = util.time_stamp('''2000-01-01 02:00:00''')
    await controller.set_end_time(util.epoch(am_2))

    # set end time request #B: (1am, 3am)
    am_3 = util.time_stamp('''2000-01-01 03:00:00''')
    await controller.set_end_time(util.epoch(am_3))

    # controller recevies data for the request #B first
    data_2nd_req = temperature_data_lst(24)
    controller.receive_temperature_data(
        util.epoch(am_1), util.epoch(am_3), 300, data_2nd_req
    )

    # note there was a rendering as usual

    # receives data for the 1st request
    data_1st_req = temperature_data_lst(60)
    controller.receive_temperature_data(
        util.epoch(am_1), util.epoch(am_2), 60, data_1st_req
    )

    # this time, there was no rendering

    # the end, thank you










