from abc import ABCMeta, abstractmethod


class abstractclassmethod(classmethod):
    __isabstractmethod__ = True

    def __init__(self, callable):
        callable.__isabstractmethod__ = True
        super(abstractclassmethod, self).__init__(callable)


class BaseContestFormat(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, contest, config):
        self.config = config
        self.contest = contest

    @property
    @abstractmethod
    def name(self):
        """
        Name of this contest format. Should be invoked with gettext_lazy.

        :return: str
        """
        raise NotImplementedError()

    @abstractclassmethod
    def validate(cls, config):
        """
        Validates the contest format configuration.

        :param config: A dictionary containing the configuration for this contest format.
        :return: None
        :raises: ValidationError
        """
        raise NotImplementedError()

    @abstractmethod
    def update_participation(self, participation):
        """
        Updates a ContestParticipation object's score, cumtime, and format_data fields based on this contest format.
        Implementations should call ContestParticipation.save().

        :param participation: A ContestParticipation object.
        :return: None
        """
        raise NotImplementedError()

    def get_format_data_for_api(self, entry, problem_points, frozen=False):
        """
        Returns a sanitized copy of a single problem's format_data entry safe to expose via the ranking JSON API.
        When frozen=True, formats that support scoreboard freezing should strip post-freeze results so they are
        not leaked to end users. The default implementation returns the entry unchanged (no freeze support).

        :param entry: A dict — one problem's format_data entry for a single participation.
        :param problem_points: Maximum points for the problem (used by some formats to detect pre-freeze AC).
        :param frozen: Whether to apply freeze sanitisation (True when the scoreboard is currently frozen).
        :return: A dict safe to serialise and send to the browser.
        """
        return entry

    @abstractmethod
    def get_problem_breakdown(self, participation, contest_problems):
        """
        Returns a machine-readable breakdown for the user's performance on every problem.

        :param participation: The ContestParticipation object.
        :param contest_problems: The list of ContestProblem objects to display performance for.
        :return: A list of dictionaries, whose content is to be determined by the contest system.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_label_for_problem(self, index):
        """
        Returns the problem label for a given zero-indexed index.

        :param index: The zero-indexed problem index.
        :return: A string, the problem label.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_short_form_display(self):
        """
        Returns a generator of Markdown strings to display the contest format's settings in short form.

        :return: A generator, where each item is an individual line.
        """
        raise NotImplementedError()

