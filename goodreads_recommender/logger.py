from goodreads_recommender.services.config_service import ConfigService


class Logger:
    def __init__(self, config_service: ConfigService):
        self.config_service = config_service

    def log(self, *message):
        print(*message)

    def verbose(self, *message):
        if not self.config_service.verbose:
            return

        print("\x1b[0;34m" + " ".join(message) + "\x1b[0m")

    def important(self, *message):
        print("\x1b[0;35m" + " ".join(message) + "\x1b[0m")
