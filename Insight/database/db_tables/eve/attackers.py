from .base_objects import *
from . import characters,corporations,alliances,types


class Attackers(dec_Base.Base):
    __tablename__ = 'attackers'

    no_pk = Column(Integer,primary_key=True,autoincrement=True,nullable=False)
    kill_id = Column(Integer,ForeignKey("kills.kill_id"),nullable=False, autoincrement=False)
    character_id = Column(Integer,ForeignKey("characters.character_id"),default=None, nullable=True)
    corporation_id = Column(Integer,ForeignKey("corporations.corporation_id"), default=None, nullable=True)
    alliance_id = Column(Integer,ForeignKey("alliances.alliance_id"), default=None, nullable=True)
    damage_done = Column(Float, default=0.0, nullable=False)
    final_blow = Column(Boolean, default=False, nullable=False)
    security_status = Column(Float, default=0.0, nullable=False)
    ship_type_id = Column(Integer,ForeignKey("types.type_id"), default=None, nullable=True)
    weapon_type_id = Column(Integer,ForeignKey("types.type_id"),default=None, nullable=True) #not compared with anything

    object_kill = relationship("Kills",uselist=False,back_populates="object_attackers")
    object_pilot = relationship("Characters",uselist=False,back_populates="object_attackers",lazy="joined")
    object_corp = relationship("Corporations",uselist=False,back_populates="object_attackers",lazy="joined")
    object_alliance = relationship("Alliances",uselist=False,back_populates="object_attackers",lazy="joined")
    object_ship = relationship("Types",uselist=False,foreign_keys=[ship_type_id],back_populates="object_attacker_ships",lazy="joined")
    object_weapon = relationship("Types",uselist=False,foreign_keys=[weapon_type_id],back_populates="object_attacker_weapons",lazy="joined")

    def __init__(self, data: dict):
        self.character_id = data.get("character_id")
        self.corporation_id = data.get("corporation_id")
        self.alliance_id = data.get("alliance_id")
        self.damage_done = data.get("damage_done")
        self.final_blow = data.get("final_blow")
        self.security_status = data.get("security_status")
        self.ship_type_id = data.get("ship_type_id")
        self.weapon_type_id = data.get("weapon_type_id")

        self.load_objects()

    def compare_ship_value(self, other):
        try:
            if self.object_ship is None:
                return False
            if other.object_ship is None:
                return True
            if self.object_ship.basePrice is None:
                return False
            if other.object_ship.basePrice is None:
                return True
            return self.object_ship.basePrice >= other.object_ship.basePrice
        except Exception as ex:
            print(ex)
            return False

    def load_objects(self):
        if self.character_id:
            self.object_pilot = characters.Characters(self.character_id)
        if self.corporation_id:
            self.object_corp = corporations.Corporations(self.corporation_id)
        if self.alliance_id:
            self.object_alliance = alliances.Alliances(self.alliance_id)
        if self.ship_type_id:
            self.object_ship = types.Types(self.ship_type_id)
        if self.weapon_type_id:
            self.object_weapon = types.Types(self.weapon_type_id)

    def compare_filter_list(self, other):
        if isinstance(other,tb_Filter_characters):
            return self.character_id == other.filter_id
        if isinstance(other,tb_Filter_corporations):
            return self.corporation_id == other.filter_id
        if isinstance(other,tb_Filter_alliances):
            return self.alliance_id == other.filter_id
        if isinstance(other,tb_Filter_types):
            return self.ship_type_id == other.filter_id
        if isinstance(other,tb_Filter_groups):
            try:
                compare: tb_types = self.object_ship
                return compare.group_id == other.filter_id
            except Exception as ex:
                return False
        if isinstance(other,tb_Filter_categories):
            try:
                compare: tb_groups = self.object_ship.object_group
                return compare.category_id == other.filter_id
            except Exception as ex:
                return False
        return False



from ..filters import *
from ..eve import *