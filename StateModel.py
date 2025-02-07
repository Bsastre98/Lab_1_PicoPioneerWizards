"""
# StateModel.py
# A State model implementation
# Author: Arijit Sengupta
"""
import time
from Log import *

class StateModel:
    """
    A really simple implementation of a generic state model
    Keeps track of a number of states by sending the total number
    of states to the constructor. State numbers always start from 0
    which is the start state.

    Also takes a handler which is just a reference to a class that has
    three responder methods. The responder methods for stateEntered and
    stateLeft receives the state that was entered or left,
    with the event code that caused it. stateDo only receives the current
    state.
    
        stateEntered(state, event) : perform entry actions for the state
        stateLeft(state, event)    : perform exit actions for the state
        stateEvent(state, event)   : perform in-state event response 
        stateDo(state)             : perform a single loop of state activity

    Note that state transitions take precedence over in-state events. So try to
    ensure that you don't have the same event causing a transition as well as an in-state
    event, since the in-state event will never be called.

    Currently the following types of events are supported.
    
    * Button events - these are created by calling the addButton method. The button's
      existing handler will be replaced with the model's handler, and two events of the
      following form will be enabled: [name]_press and [name]_release. Note
      that two buttons cannot have the same name.
    * Timer events - these are generated by software or hardware timers. Created by calling
      the addTimer method - will create an event [name}_timeout. Again, two timers
      cannot have the same name.
    * "no_event" is for non-event-related transitions. So if a state performs 
       the entry actions and do actions and then immediately goes to the next state, 
       no_event can be used.
    * Custom events - if a condition event needs to be executed, call the addCustomEvent
      method with the name of the event. This name can now be used for transitions, but the
      Controller must check the condition itself, and then call processEvent("eventname")
      when the codnition is satisfied.

    The calling class or the handler must override stateEntered and
    stateLeft to perform actions as per the state model

    After creating the state, call addTransition to determine
    how the model transitions from one state to the next.

    As events start coming in, call processEvent on the event to
    have the state model transition as per the transition matrix.
    """
    
    def __init__(self, numstates, handler, debug=False):
        """
        The statemodel constructor - needs 2 things minimum:
        Parameters
        ----------
        numstates - the number of states in the State model (includes the start and end states)
        handler - the handler class that should implement the model actions stateEntered and stateLeft
         - stateEntered will receive as parameter which state the model has entered - this should
            allow the handler to execute entry actions
         - stateLeft will receive as parameter which state the model left - this will allow the handler
            to execute the exit actions.
        all continuous in-state actions must be implemented in the handler in a execute loop.
        
        debug will print things to the screen like active state, transitions, events, etc.
        """
        
        self._numstates = numstates
        self._running = False
        self._transitions = []
        for i in range(0, numstates):
            self._transitions.append(None)
        self._curState = -1
        self._handler = handler
        self._debug = debug
        self._events = ['no_event']
        self._buttons = []
        self._timers = []

    def addTransition(self, fromState, events, toState):
        """
        Add a transition to the state model. The transition is defined by the
        source state, an array of events that will cause the transition, and the
        destination state. The events array can have multiple events that will all
        cause the same transition.
        """

        for event in events:
            if event in self._events:
                if not self._transitions[fromState]:
                    self._transitions[fromState] = []
                self._transitions[fromState].append((event,toState))
            else:
                raise ValueError(f"Invalid event {event}")
            
    def setTransitionTable(self, transitions):
        """
        Set the entire transition table at once. The transitions should be in the form
        of a matrix of tuples. Each row of the matrix corresponds to one source state
        and the values in the matrix should be in the form of a tuple (event, destination).

        For example, if you have 3 states and the transitions are as follows:
        0 -> 1 on event1, 0 -> 2 on event2, 1 -> 2 on event3, 2 -> 0 on event4, 2 -> 1 on event5

        Then the transition matrix should be:
        [
            [(event1, 1), (event2, 2)],
            [(event3, 2)],
            [(event4, 0), (event5, 1)]
        ]

        Note that only basic error checks are performed in this method. It is the responsibility
        of the calling class to ensure that the transition table is correct.
        """

        # Check if the number of rows in the transition matrix is the same as the number of states
        if len(transitions) != self._numstates:
            self._numstates = len(transitions)
            Log.e(f"Number of states in the transition matrix does not match the number of states in the model. Resetting the number of states to {self._numstates}")
        # Check if the events are valid
        for row in transitions:
            for (e,s) in row:
                if e not in self._events:
                    raise ValueError(f"Invalid event {e}")

        self._transitions = transitions

    def getTransition(self, fromState, event):
        """
        Get the distination for this transition
        """

        for (e,s) in self._transitions[fromState]:
            if e == event:
                return s
        return -1
        
    
    def start(self):
        """ start the state model - always starts at state 0 as the start state """
        
        self._curState = 0
        self._running = True
        self._handler.stateEntered(self._curState, "no_event")  # start the state model

    def stop(self):
        """
        stop the state model - this will call the handler one last time with
        what state was stopped at, and then set the running flag to false.
        """
    
        if self._running:
            self._handler.stateLeft(self._curState, "no_event")
        self._running = False
        for b in self._buttons:
            b.setHandler(None)
        for t in self._timers:
            t.setHandler(None)
            t.cancel()
        self._curState = -1

    def gotoState(self, newState, event="no_event"):
        """
        force the state model to go to a new state. This may be necessary to call
        in response to an event that is not automatically handled by the Model class.
        This will correctly call the stateLeft and stateEntered handlers
        """
        
        if (newState < self._numstates):
            if self._debug:
                Log.d(f"Going from State {self._curState} to State {newState} on event {event}")
            self._handler.stateLeft(self._curState, event)
            self._curState = newState
            self._handler.stateEntered(self._curState, event)

    def processEvent(self, event):
        """
        Get the model to process an event. The event should be one of the events defined
        at the top of the model class. Currently 4 button press and release events, and
        a timeout event is supported. Handlers for the buttons and the timers should be
        incorporated in the main class, and processevent should be called when these handlers
        are triggered.
        
        I may try to improve this design a bit in the future, but for now this is how it is
        built.
        """
        
        if (event in self._events):
            
            newstate = self.getTransition(self._curState, event)
            if newstate >= 0:
                if self._debug:
                    Log.d(f"Processing event {event}")
                self.gotoState(newstate, event)
            else:
                if self._debug:
                    if event != "no_event":
                        if not self._handler.stateEvent(self._curState, event):
                            Log.d(f"Ignoring event {event}")                    
        else:
            raise ValueError(f"Invalid event {event}")

    def run(self, delay=0.1):        
        # Start the model first
        self.start()
        # Then it should do a continous loop while the model runs
        while self._running:
            # Inside, you can use if statements do handle various do/actions
            # that you need to perform for each state
            # Do not perform entry and exit actions here - those are separate
                        
            self._handler.stateDo(self._curState)

            # Ping any software timer in the model
            for timer in self._timers:
                if type(timer).__name__ == 'SoftwareTimer':
                    timer.check()
            
            # I suggest putting in a short wait so you are not overloading the poor Pico
            if delay > 0:
                time.sleep(delay)

            # If there is any no_event transition, lets process that now
            self.processEvent("no_event")


    def addButton(self, btn):
        btnname = btn._name
        event1 = f'{btnname}_press'
        event2 = f'{btnname}_release'
        
        if event1 in self._events or event2 in self._events:
            raise ValueError(f'There is already a button with the name {btnname}')
        else:
            self._events.append(event1)
            self._events.append(event2)
            btn.setHandler(self)
            self._buttons.append(btn)            

    def buttonPressed(self, name):
        """ 
        The internal button handler - now Model can take care of buttons
        that have been added using the addButton method.
        """

        self.processEvent(f'{name}_press')

    def buttonReleased(self, name):
        """
        Same thing with Button release, if you want to handle release events
        As well as press or just want to do release events only.
        """

        self.processEvent(f'{name}_release')
        
    def addTimer(self, timer):
        """
        Add a timer to the state model. All timers must have distinct names
        Exception will be raised if a timer with the same name is added.
        """
        
        eventname = f'{timer._name}_timeout'
        if eventname in self._events:
            raise ValueError(f'A timer with name {timer._name} already exists')
        else:
            self._events.append(eventname)
            timer.setHandler(self)
            self._timers.append(timer)

    def addCustomEvent(self, event):
        """
        Add custom events. This simply defines the event names for transition.
        The StateModel does not have the ability to detect these events - the
        Controller must detect the events and call processEvent to handle any
        transition based on the event.

        All events must have distinct names. Exception will be raised if the
        event already exists.
        """
        
        if event in self._events:
            raise ValueError(f'An event with the name {event} already exists')
        else:
            self._events.append(event)
        
    def timeout(self, name):
        """
        Internal event handler for any timeouts received from timers
        added to the model. Will cause the timername_timeout event
        to be processed by the transition table
        """
        
        eventname = f'{name}_timeout'
        self.processEvent(eventname)
