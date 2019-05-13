import logging
import time

logging.basicConfig(level=logging.DEBUG)

class MockUI:
    '''Renders a chart on screen with the given datapoints, which are simply an
    array of floating point values. Each time this method is called the chart
    is cleared and re-rendered. This is the output of your algorithm.
    You do not need to implement this method. A fully functional version of
    this function will be available in production. However, the production
    implementation is being developed in parallel by another team and is not
    available to you at this time. Utilize as necessary in your development.

    datapoints - An array of values to show on screen. A null in this
    array means is not yet data available for the given point.
    '''

    # For testing
    state = {'datapoints': [], 'last_mod': time.time()}

    @property
    def datapoints(self):
        return self.state['datapoints']

    @datapoints.setter
    def datapoints(self, new_datapoints):
        self.state['datapoints'] = new_datapoints
        self.state['last_mod'] = time.time()

    def set_chart_data(self, datapoints):
        self.datapoints = datapoints
        logging.debug('''set_chart_data: %s datapoints rendered=%s''',
                      len(datapoints), datapoints)

    @property
    def last_mod(self):
        return self.state['last_mod']

