import logging
import time
import asyncio
import util

logging.basicConfig(level=logging.DEBUG)

SIMULATE_DELAY = False

class MockBackend:
    '''Issues a call to a remote service to fetch some data. The call is
    asynchronous - you will be called back via the receiveTemperatureData
    method to get the result. Service calls are guaranteed to succeed.

    You do not need to implement this method. A fully functional version of
    this function will be available in production. However, the production
    implementation is being developed in parallel by another team and is not
    available to you at this time. Utilize as necessary in your development.

    startTime - The epoch time of the first datapoint to fetch,
    inclusive
    endTime - The epoch time of the last datapoint to fetch, exclusive
    resolution - The period, or granularity, of the data to fetch, in
    '''

    last_request = None
    last_mod = time.time()

    async def request_temperature_data(self, start_time, end_time, resolution):
        start = time.time()
        n_datapoints = util.num_datapoints(end_time - start_time, resolution)
        await asyncio.sleep(int(SIMULATE_DELAY))
        logging.debug(
            '''request_temperature_data: Took %s seconds to request %s datapoints''',
            time.time() - start, n_datapoints)
        self.last_request = (
            start_time,
            end_time,
            resolution
        )
        self.last_mod = time.time()
