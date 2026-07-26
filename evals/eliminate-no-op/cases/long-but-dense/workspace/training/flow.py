from metaflow import FlowSpec, step


class TrainFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.end)

    @step
    def end(self):
        pass
