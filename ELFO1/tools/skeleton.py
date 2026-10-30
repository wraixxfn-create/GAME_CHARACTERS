"""Scheletro di ELFO1: 43 ossa (42 deformanti) pensate per un umanoide slanciato.

Il rig e' costruito in **coordinate del sorgente** (altezza 1,0, piedi a z=0,
viso verso -Y), cosi' i landmark si leggono direttamente sulla mesh originale.
Lo step 5 scala tutto a 1,85 m.

Catena:

```
root
└─ hips ─ spine_01 ─ spine_02 ─ chest ─ neck ─ head
   │                              │              ├─ hair_crest
   │                              │              ├─ hair_back_01 ─ 02 ─ 03
   │                              │              └─ hair_side_01.L/R ─ 02
   │                              └─ clavicle.L/R ─ upperarm ─ forearm ─ hand ─ fingers / thumb
   ├─ thigh.L/R ─ shin ─ foot ─ toe
   └─ skirt_front_01 ─ 02, skirt_back_01 ─ 02, skirt_01.L/R ─ 02
```

Due dettagli che contano:

* le ossa delle **gambe** stanno dentro il gonnellone: i semi dello skinning
  finiscono sulla superficie della gamba, non sul tessuto, perche' la distanza
  geodesica dalla coscia alla stoffa passa per la vita;
* le ossa della **gonnellina** e dei **capelli** sono corte e interne al volume:
  servono solo a dare un secondo strato di movimento (swing) alle parti che il
  corpo non deve trascinare rigidamente.
"""
from mathutils import Vector

# (nome, parent, testa, coda, connessa)
CORE = [
    ("root",      None,       (0.000,  0.010, 0.000), (0.000,  0.010, 0.120), False),
    ("hips",      "root",     (0.000,  0.000, 0.465), (0.000, -0.002, 0.515), False),
    ("spine_01",  "hips",     (0.000, -0.002, 0.515), (0.000, -0.004, 0.575), True),
    ("spine_02",  "spine_01", (0.000, -0.004, 0.575), (0.000, -0.006, 0.638), True),
    ("chest",     "spine_02", (0.000, -0.006, 0.638), (0.000, -0.008, 0.735), True),
    ("neck",      "chest",    (0.000, -0.008, 0.748), (0.000, -0.016, 0.806), False),
    ("head",      "neck",     (0.000, -0.016, 0.806), (0.000, -0.024, 0.930), True),
    # capelli: cresta in cima e due code posteriori
    ("hair_crest",  "head",      (0.000, -0.004, 0.930), (0.000,  0.010, 1.000), False),
    ("hair_back_01", "head",     (0.000,  0.048, 0.900), (0.000,  0.062, 0.815), False),
    ("hair_back_02", "hair_back_01", (0.000, 0.062, 0.815), (0.000, 0.074, 0.725), True),
    ("hair_back_03", "hair_back_02", (0.000, 0.074, 0.725), (0.000, 0.082, 0.640), True),
    # gonnellone: quattro quadranti, due segmenti ciascuno
    ("skirt_front_01", "hips", (0.000, -0.075, 0.455), (0.000, -0.095, 0.315), False),
    ("skirt_front_02", "skirt_front_01", (0.000, -0.095, 0.315), (0.000, -0.108, 0.180), True),
    ("skirt_back_01",  "hips", (0.000,  0.070, 0.455), (0.000,  0.085, 0.315), False),
    ("skirt_back_02",  "skirt_back_01", (0.000, 0.085, 0.315), (0.000, 0.096, 0.180), True),
]

# ossa del lato ".L" (x > 0); il lato ".R" e' lo specchio su X
SIDE = [
    # spalla e braccio (posa A, braccia aperte ~45 gradi)
    ("clavicle", "chest",    (0.016, -0.012, 0.735), (0.096, -0.008, 0.718), False),
    ("upperarm", "clavicle", (0.096, -0.008, 0.718), (0.176, -0.024, 0.615), True),
    ("forearm",  "upperarm", (0.176, -0.024, 0.615), (0.228, -0.052, 0.548), True),
    ("hand",     "forearm",  (0.228, -0.052, 0.548), (0.246, -0.072, 0.508), True),
    # la mano del modello ha le dita fuse in una "manopola": una sola catena
    # per le dita piu' un pollice, quanto basta per aprire/chiudere la presa
    ("fingers",  "hand",     (0.246, -0.072, 0.508), (0.254, -0.088, 0.468), False),
    ("thumb",    "hand",     (0.238, -0.048, 0.524), (0.230, -0.080, 0.496), False),
    # gamba
    ("thigh", "hips",  (0.058,  0.000, 0.455), (0.076, -0.012, 0.262), False),
    ("shin",  "thigh", (0.076, -0.012, 0.262), (0.093,  0.012, 0.068), True),
    ("foot",  "shin",  (0.093,  0.012, 0.068), (0.095, -0.040, 0.020), True),
    ("toe",   "foot",  (0.095, -0.040, 0.020), (0.096, -0.066, 0.014), True),
    # capelli laterali e gonnellone laterale
    ("hair_side_01", "head", (0.055, 0.012, 0.905), (0.072, 0.022, 0.812), False),
    ("hair_side_02", "hair_side_01", (0.072, 0.022, 0.812), (0.081, 0.032, 0.712), True),
    ("skirt_01", "hips",  (0.095, 0.000, 0.455), (0.115, 0.000, 0.315), False),
    ("skirt_02", "skirt_01", (0.115, 0.000, 0.315), (0.128, 0.000, 0.180), True),
]

SIDE_NAMES = {e[0] for e in SIDE}


def mirrored(entry, suffix, sign):
    """Crea la voce per un lato: `sign=+1` -> .L, `sign=-1` -> .R (x negato)."""
    name, parent, h, t, conn = entry
    p = f"{parent}.{suffix}" if parent in SIDE_NAMES else parent
    return (f"{name}.{suffix}", p,
            (sign * h[0], h[1], h[2]), (sign * t[0], t[1], t[2]), conn)


def bone_list():
    out = list(CORE)
    for suffix, sign in (("L", 1), ("R", -1)):
        out += [mirrored(e, suffix, sign) for e in SIDE]
    return out


BONES = bone_list()
DEFORM = [b[0] for b in BONES if b[0] != "root"]


def print_tree():
    kids = {}
    for name, parent, *_ in BONES:
        kids.setdefault(parent, []).append(name)

    def walk(name, depth=0):
        print("  " * depth + name)
        for k in kids.get(name, []):
            walk(k, depth + 1)

    walk("root")


def build_armature(name="ELFO1_rig"):
    """Crea l'armatura (in edit mode) e restituisce l'oggetto."""
    import bpy

    arm_data = bpy.data.armatures.new(name)
    arm_ob = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_ob)
    bpy.context.view_layer.objects.active = arm_ob
    arm_ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones
    for bname, parent, h, t, _conn in BONES:
        b = eb.new(bname)
        b.head = Vector(h)
        b.tail = Vector(t)
        b.use_deform = bname != "root"
    for bname, parent, _h, _t, conn in BONES:
        if parent:
            eb[bname].parent = eb[parent]
            eb[bname].use_connect = conn
    # roll coerente: gli arti con l'asse X verso l'esterno, il resto su +X
    for b in eb:
        if b.name.startswith(("upperarm", "forearm", "thigh", "shin", "skirt",
                              "hair_side")):
            b.align_roll(Vector((0, 0, 1)))
        else:
            b.align_roll(Vector((0, -1, 0)))
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm_ob
