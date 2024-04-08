import random
import sys
from abc import abstractmethod
from math import sqrt


class Map(object):
    def __init__(self):
        self.width = 16000
        self.height = 9000

    @abstractmethod
    def get_ghosts(self):
        """
        :rtype: list of Ghost
        """
        return []

    @abstractmethod
    def get_allies(self):
        """
        :rtype: list of Buster
        """
        return []

    @abstractmethod
    def get_enemies(self):
        """
        :rtype: list of Buster
        """
        return []


class GameController(object):
    @abstractmethod
    def move_to(self, pos, message=''):
        pass

    @abstractmethod
    def release(self, message=''):
        pass

    @abstractmethod
    def stun(self, enemy, message=''):
        pass

    @abstractmethod
    def bust(self, ghost, message=''):
        pass


class STDGameController(GameController):
    INSTANCE = None  # type: GameController

    def __init__(self, **kwargs):
        self.stdout = kwargs.get('stdout', sys.stdout)
        self.debug = kwargs.get('debug', False)

    def bust(self, ghost, message=''):
        self.stdout.write('BUST {}{}\n'.format(ghost.id, self.get_debug(message)))

    def move_to(self, pos, message=''):
        self.stdout.write('MOVE {} {}{}\n'.format(pos[0], pos[1], self.get_debug(message)))

    def release(self, message=''):
        self.stdout.write('RELEASE{}\n'.format(self.get_debug(message)))

    def stun(self, enemy, message=''):
        self.stdout.write('STUN {}\n'.format(enemy.id, self.get_debug(message)))

    def get_debug(self, message):
        if self.debug and message:
            return ' ' + message
        return ''


STDGameController.INSTANCE = STDGameController(debug=True)


class MapObject(object):
    def __init__(self, **kwargs):
        self.pos = kwargs.get('pos', (0, 0))

    def set_pos(self, x, y):
        self.pos = (x, y)

    def distance_from(self, obj):
        dx = self.pos[0] - obj.pos[0]
        dy = self.pos[1] - obj.pos[1]
        return dx * dx + dy * dy

    def is_in_range(self, obj, scope):
        close, far = scope
        return close * close <= self.distance_from(obj) < far * far

    def is_within(self, obj, radius):
        return self.is_in_range(obj, (0, radius))


class Base(MapObject):
    def __init__(self, **kwargs):
        super(Base, self).__init__(**kwargs)
        self.range = kwargs.get('range', (0, 1600))

    def is_close_to(self, obj):
        return self.is_in_range(obj, self.range)


class MapActor(MapObject):
    def __init__(self, **kwargs):
        super(MapActor, self).__init__(**kwargs)
        self.id = kwargs.get('id', 0)
        self.is_seen = kwargs.get('is_seen', False)
        self.is_known = kwargs.get('is_known', self.is_seen)

    def get_closest_of(self, actors):
        distances = {}

        for actor in actors:
            distances[actor] = self.distance_from(actor)

        min_dist = min(distances.values())

        return [a for a, d in distances.items() if d == min_dist]

    @abstractmethod
    def reset(self):
        pass


class Ghost(MapActor):
    def __init__(self, **kwargs):
        super(Ghost, self).__init__(**kwargs)
        self.stamina = kwargs.get('stamina', 0)
        self.attacking_busters = kwargs.get('attacking_busters', 0)

    def reset(self):
        self.is_seen = False

    def remaining_stamina(self):
        return self.stamina

    def forget(self):
        self.is_known = False


class Strategy(object):
    def __init__(self, **kwargs):
        self.buster = kwargs.get('buster', None)  # type: Buster
        self.map = kwargs.get('map', Map())  # type Map
        self.controller = kwargs.get(
            'controller', GameController())  # type: GameController

    @abstractmethod
    def is_applicable(self):
        """
        :rtype: bool
        """
        return False

    @abstractmethod
    def execute(self):
        pass


class SeekingStrategy(Strategy):
    def __init__(self, **kwargs):
        super(SeekingStrategy, self).__init__(**kwargs)
        self.seek_pos = self.generate_random_position()
        self.counter = 0
        self.corners = [(16000, 0), (0, 0), (0, 9000), (16000, 9000)]
        self.corners = self.corners[self.buster.id:] + self.corners[:self.buster.id]

    def is_applicable(self):
        return True

    def execute(self):
        if self.buster.pos == self.seek_pos:
            if self.counter:
                self.seek_pos = self.generate_random_position()
                self.counter -= 1
            else:
                self.seek_pos = self.corners[0]
                self.corners = self.corners[1:] + self.corners[:1]
                self.counter = 5

        self.controller.move_to(self.seek_pos,
                                "Search at %d:%d" % self.seek_pos)

    @staticmethod
    def generate_random_position():
        return random.randrange(0, 16000), random.randrange(9000)


class HomingStrategy(Strategy):
    def is_applicable(self):
        return self.buster.captured_ghost is not None

    def execute(self):
        self.controller.move_to(self.buster.base.pos, "Going home")


class ReleaseStrategy(Strategy):
    def is_applicable(self):
        return self.buster.captured_ghost is not None and \
               self.buster.base.is_close_to(self.buster)

    def execute(self):
        self.controller.release("Release %d" % self.buster.captured_ghost.id)
        self.buster.captured_ghost.is_known = False


class InterceptStrategy(Strategy):
    def __init__(self, **kwargs):
        super(InterceptStrategy, self).__init__(**kwargs)

        self.closest_ghost = None

    def is_applicable(self):
        for ghost in self.get_known_ghosts():
            if self.buster.pos == ghost.pos:
                ghost.forget()
            else:
                return True
        return False

    def get_known_ghosts(self):
        return [ghost for ghost in self.map.get_ghosts() if ghost.is_known]

    def execute(self):
        known_ghosts = self.get_known_ghosts()
        closest_ghosts = self.buster.get_closest_of(known_ghosts)
        closest_ghost = min(closest_ghosts, key=lambda g: g.stamina)
        self.controller.move_to(closest_ghost.pos,
                                "Intercept %d" % closest_ghost.id)


class StunStrategy(Strategy):
    def __init__(self, **kwargs):
        super(StunStrategy, self).__init__(**kwargs)
        self.enemy = None

    def is_applicable(self):
        enemies = [e for e in self.map.get_enemies() if self.buster.can_stun(e)]

        if not enemies:
            return False

        ghost_carrying_enemies = [e for e in enemies if e.has_captured_ghost()]

        if ghost_carrying_enemies:
            self.enemy = ghost_carrying_enemies[0]
            return True

        self.enemy = enemies[0]
        return True

    def execute(self):
        self.buster.stun_charge = 0
        self.controller.stun(self.enemy, "Stun %d" % self.enemy.id)


def copy_of(obj):
    return obj.__class__(**obj.__dict__)


class ChasingStrategy(Strategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.enemy = None
        self.pos = None

    def is_applicable(self):
        for enemy in self.ghost_carrying_enemies():
            clone_buster = copy_of(self.buster)
            clone_enemy = copy_of(enemy)
            base = enemy.base

            while self.enemy_keeps_ghost(clone_enemy, clone_buster, base):
                clone_enemy.step_towards(base.pos)
                clone_buster.step_towards(clone_enemy.pos)

            if base.is_close_to(clone_enemy):
                continue

            self.enemy = enemy
            self.pos = clone_enemy.pos
            return True

        return False

    def enemy_keeps_ghost(self, enemy, buster, base):
        return not (buster.can_stun(enemy) or base.is_close_to(enemy))

    def ghost_carrying_enemies(self):
        return [e for e in self.map.get_enemies() if
                e.is_known and e.has_captured_ghost()]

    def execute(self):
        self.controller.move_to(self.pos, 'Chasing %d' % self.enemy.id)


class BackingStrategy(Strategy):
    def __init__(self, **kwargs):
        super(BackingStrategy, self).__init__(**kwargs)
        self.ghost = None

    def is_applicable(self):
        for ghost in self.map.get_ghosts():
            if ghost.is_seen and self.buster.is_too_close_to(ghost):
                self.ghost = ghost
                return True

        return False

    def execute(self):
        pos = self.calculate_closest_in_range_point()
        self.controller.move_to(pos,
                                "Back to %d:%d" % pos)

    def calculate_closest_in_range_point(self):
        min_dist = self.buster.bust_range[0] + 1
        return self.keep_distance(self.buster, self.ghost, min_dist)

    @staticmethod
    def keep_distance(player, enemy, min_dist):
        px, py = player.pos
        ex, ey = enemy.pos

        dx = px - ex
        dy = py - ey

        dist = sqrt(dx * dx + dy * dy)

        if dist > 0:
            px = ex + int(min_dist * dx / dist)
            py = ey + int(min_dist * dy / dist)
        else:
            px = random.randrange(0, 160000)
            py = random.randrange(0, 9000)

        return px, py


class FleeingStrategy(BackingStrategy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.enemies = []

    def is_applicable(self):
        self.enemies = [e for e in self.map.get_enemies() if self.will_be_able_to_stun(e, self.buster)]

        if self.enemies and self.buster.stun_charge < 19:
            return True

        return False

    def will_be_able_to_stun(self, enemy, buster):
        if not enemy.is_seen or enemy.stun_charge < 19 or enemy.stunned_counter >= 1:
            return False

        min_distance = enemy.stun_range[1] + enemy.speed
        return self.is_in_range(buster, enemy, min_distance)

    @staticmethod
    def is_in_range(buster, enemy, min_distance):
        dist = buster.distance_from(enemy)
        return dist <= min_distance ** 2

    def execute(self):
        mean_enemy = self.means_of_enemies()

        min_distance = mean_enemy.stun_range[1] + mean_enemy.speed + 1
        pos = self.keep_distance(self.buster, mean_enemy, min_distance)
        self.controller.move_to(pos, "Fleeing to %d:%d" % pos)

    def means_of_enemies(self):
        mean_enemy = Buster()
        x, y = self.mean_pos_of_enemies()
        e = self.enemies[0]
        mean_enemy.pos = x, y
        mean_enemy.speed = e.speed
        mean_enemy.stun_range = e.stun_range
        return mean_enemy

    def mean_pos_of_enemies(self):
        x, y = 0, 0
        for e in self.enemies:
            ex, ey = e.pos
            x += ex
            y += ey
        x //= len(self.enemies)
        y //= len(self.enemies)
        return x, y


class BustingStrategy(Strategy):
    def __init__(self, **kwargs):
        super(BustingStrategy, self).__init__(**kwargs)
        self.ghost = None

    def is_applicable(self):
        ghosts = [g for g in self.map.get_ghosts() if self.buster.can_bust(g)]

        if not ghosts:
            return False

        self.ghost = min(ghosts, key=lambda g: g.stamina)
        return True

    def execute(self):
        players = len(self.map.get_enemies()) + len(self.map.get_allies())
        if self.ghost.attacking_busters == players:
            self.controller.move_to(self.ghost.pos)
        else:
            self.controller.bust(self.ghost, "Bust %d" % self.ghost.id)


class Buster(MapActor):
    STRATEGIES = [
        StunStrategy,
        ReleaseStrategy,
        HomingStrategy,
        ChasingStrategy,
        BustingStrategy,
        FleeingStrategy,
        BackingStrategy,
        InterceptStrategy,
        SeekingStrategy,
    ]

    def __init__(self, **kwargs):
        super(Buster, self).__init__(**kwargs)
        self.captured_ghost = kwargs.get('captured_ghost', None)
        self.map = kwargs.get('map', None)
        self.base = kwargs.get('base', Base())
        self.stun_range = kwargs.get('stun_range', (0, 1760))
        self.stun_charge = kwargs.get('stun_charge', 0)
        self.stunned_counter = kwargs.get('stunned_counter', 0)
        self.bust_range = kwargs.get('bust_range', (900, 1760))
        self.busting_ghost = kwargs.get('busting_ghost', None)
        self.speed = kwargs.get('speed', 800)

        controller = kwargs.get('controller', STDGameController.INSTANCE)

        self.strategies = []  # type: list of Strategy
        for strategy_class in Buster.STRATEGIES:
            self.strategies.append(
                strategy_class(
                    buster=self,
                    map=self.map,
                    controller=controller
                )
            )

    def step(self):
        for strategy in self.strategies:
            if strategy.is_applicable():
                strategy.execute()
                break

    def step_towards(self, goal):
        self.pos = self.next_step_between(self.pos, goal, self.speed)

    @staticmethod
    def next_step_between(start, end, speed):
        sx, sy = start
        ex, ey = end

        dx, dy = ex - sx, ey - sy
        dist = dx * dx + dy * dy

        if dist <= speed ** 2:
            return ex, ey

        dist = sqrt(dist)
        return int(sx + (speed * dx / dist)), int(sy + (speed * dy / dist))

    def can_stun(self, buster):
        return self.stun_charge >= 20 and \
               not buster.is_stunned() and \
               buster.is_seen and \
               self.is_in_range(buster, self.stun_range)

    def can_bust(self, ghost):
        return ghost.is_seen and self.is_in_range(ghost, self.bust_range)

    def bust(self, ghost):
        self.busting_ghost = ghost

    def is_too_close_to(self, ghost):
        return self.is_within(
            ghost,
            self.bust_range[0]
        )

    def is_busting(self, ghost=None):
        if ghost is None:
            return self.busting_ghost is not None
        return self.busting_ghost == ghost

    def has_captured_ghost(self, ghost=None):
        if ghost is None:
            return self.captured_ghost is not None
        return self.captured_ghost == ghost

    def is_stunned(self):
        return self.stunned_counter != 0

    def capture(self, ghost):
        self.captured_ghost = ghost
        ghost.is_known = False
        ghost.is_seen = False

    def stunned_for(self, value):
        self.stunned_counter = value

    def reset(self):
        self.stunned_counter = 0
        self.stun_charge += 1
        self.is_seen = False


class ParsedMap(Map):
    def __init__(self, **kwargs):
        super().__init__()
        self.input = kwargs.get('input', input)
        self.ally_team = None
        self.team0 = []
        self.team1 = []
        self.ghosts = []

    def read_initials(self):
        players_per_team = int(self.input())
        number_of_ghosts = int(self.input())
        self.ally_team = int(self.input())

        for i in range(players_per_team):
            self.team0.append(
                Buster(
                    id=i,
                    base=Base(pos=(0, 0)),
                    map=self
                )
            )
            self.team1.append(
                Buster(
                    id=i + players_per_team,
                    base=Base(pos=(16000, 9000)),
                    map=self
                )
            )

        for i in range(number_of_ghosts):
            self.ghosts.append(Ghost(id=i))

    def read_round(self):
        length = int(self.input())

        for actor in self.get_actors():
            actor.reset()

        for i in range(length):
            line = self.input()
            aid, x, y, atype, state, value = map(int, line.split())
            actor = self.get_actor(aid, atype)
            actor.set_pos(x, y)
            actor.is_seen = True
            actor.is_known = True
            if atype >= 0:
                self.update_buster(actor, state, value)
            else:
                self.update_ghost(actor, state, value)

        for actor in self.get_enemies():
            if not actor.is_seen and actor.is_known:
                actor.step_towards(actor.base.pos)

    def get_actors(self):
        """
        :rtype: list of MapActor
        """
        return self.get_allies() + self.get_enemies() + self.get_ghosts()

    def update_ghost(self, ghost, state, value):
        """
        :type ghost: Ghost
        :type state: int
        :type value: int
        """
        ghost.stamina = state
        ghost.attacking_busters = value

    def update_buster(self, buster, state, value):
        """
        :type buster: Buster
        :type state: int
        :type value: int
        """
        if state == 1:
            buster.capture(self.get_ghosts()[value])
        else:
            buster.captured_ghost = None

        if state == 2:
            if buster in self.get_allies() and value == 10:
                enemies = [e for e in self.get_enemies() if e.can_stun(buster)]
                if len(enemies) == 1:
                    enemies[0].stun_charge = 0

            buster.stunned_for(value)

        if state == 3:
            buster.bust(self.get_ghosts()[value])

    def get_actor(self, oid, otype):
        if otype == 0:
            return self.team0[oid]
        elif otype == 1:
            return self.team1[oid - len(self.team0)]
        return self.ghosts[oid]

    def get_allies(self):
        """
        :rtype: list of Buster
        """
        if self.ally_team:
            return self.team1
        return self.team0

    def get_enemies(self):
        """
        :rtype: list of Buster
        """
        if self.ally_team:
            return self.team0
        return self.team1

    def get_ghosts(self):
        """
        :rtype: list of Ghost
        """
        return self.ghosts


class MainLoop(object):
    def __init__(self, **kwargs):
        self.map = kwargs.get('map', ParsedMap())

    def start(self):
        self.map.read_initials()

        try:
            while True:
                self.map.read_round()
                busters = self.map.get_allies()
                for buster in busters:
                    buster.step()
        except EOFError:
            pass

loop = MainLoop()
loop.start()

