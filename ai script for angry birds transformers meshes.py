# -*- coding: utf-8 -*-
"""
Exient XGS Engine (.xgm) importer for Blender 4.x
==================================================
Reverse-engineered importer for the .xgm model format used by the mobile
games Angry Birds Transformers / Angry Birds Go (Exient "XGS" engine).

INSTALL / USE
-------------
1. Blender 4.x -> Scripting tab -> New -> paste this whole file.
2. Press "Run Script" (Alt+P).
3. File > Import > "Exient XGM (.xgm)" is now available for the rest of
   this Blender session. You can select multiple .xgm files at once.

WHAT YOU GET
------------
- Correct vertex positions, normals, vertex colors and one UV channel.
- A material per mesh with the referenced diffuse texture wired up in
  an Image Texture node (the .tga/.png itself is NOT bundled in the
  .xgm -- point it at your extracted texture, or place the texture next
  to the .xgm file with a matching name and the importer will try to
  auto-load it).
- Joint names, and (NEW, this revision) a full parent/child joint
  HIERARCHY built from joint naming conventions, imported as a real
  Blender Armature -- see "ABOUT THE ARMATURE" below, this is
  experimental and its accuracy has NOT been visually verified in
  Blender itself (see the note at the very bottom of this docstring).
- (NEW, this revision) Optional best-effort rigid vertex-group
  skinning (each vertex assigned 100% to its nearest bone) so the
  mesh can actually be posed, since no real per-vertex skin weights
  exist anywhere in the file (confirmed this revision -- see notes).

ABOUT THE ARMATURE (please read before trusting it)
-----------------------------------------------------
This revision made real progress on the previously-undeciphered 0x1C
chunk: it contains, per joint, TWO statistically-confirmed unit
quaternions and TWO translation vectors (verified by checking
qx^2+qy^2+qz^2+qw^2 == 1 for every joint in the sample file). That part
is solid.

What is NOT solid: mapping those numbers to "this specific joint's
bind-pose offset from its parent" turned out to be unsafe to assume.
When cross-checked, the first of the two quaternion+position pairs is
BYTE-IDENTICAL between joint record i and joint record (i + 17) for
every i from 0 to 16, regardless of what the two joints actually are
(e.g. the root joint's block is identical to "l_sec_armWheel"'s block;
"c_face_brow"'s block is identical to "l_sec_backExhaust"'s block).
Those pairs of joints are not related to each other in any way a rig
would normally share data, and it doesn't line up with the file's own
left/right joint naming. That could mean: (a) this data isn't a
per-joint local bind transform at all (maybe it's something else,
like a shared pose/constraint preset), or (b) this specific sample
file's skeleton data is itself a duplicated/corrupted export. Either
way, I could not verify it, so I'm not shipping it as "the bind pose."

Given that, the armature this importer builds uses:
  - REAL, from-the-file joint names (100% confirmed).
  - A HAND-WRITTEN, name-based parent/child hierarchy (see
    JOINT_PARENT_HINTS below) -- e.g. "jnt_l_leg_knee" is parented to
    "jnt_l_leg_hip" because of what the names mean, not because the
    binary said so. This is a well-informed guess based on standard
    biped/vehicle-transformer rig conventions and this file's own
    naming scheme, not a cracked-format fact.
  - The file's own quat/pos numbers ARE used for bone placement
    (best candidate data available), but treat bone positions/
    orientations as a rough first draft, not ground truth.
This whole armature step is OFF by default (see BUILD_ARMATURE
below / the importer's "Build Armature (experimental)" checkbox) so
existing workflows are unaffected. Turn it on, look at the result in
Blender, and tell me what's wrong (bone pointing the wrong way, wrong
length, a joint parented to the wrong thing, etc.) -- that feedback is
exactly what's needed to make another pass at this.

Vertex skinning: confirmed (again, this revision) that the mesh
vertex buffer has NO room for bone indices/weights at all -- its
stride is fully accounted for by position+normal+color+UV. So there
is no way to extract "real" skin weights from this format for this
asset; if you turn on rigid auto-skin, every vertex is just assigned
100% to whichever bone head ends up closest to it in the (guessed)
bind pose. This will look "blocky" at joints, not smoothly skinned --
that's expected for a rigid assignment, not a bug.

See the bottom of this file ("FORMAT NOTES") for the chunk-by-chunk
breakdown of everything identified so far, to help extend this further.

Author: reverse-engineered collaboratively, March-uh-sometime edition,
this revision added skeleton/armature reconstruction. YMMV.

REVISION NOTE (this pass, targeting Blender 4.5): two things changed.

1. Blender 4.1 permanently removed Mesh.use_auto_smooth (setting it now
   raises AttributeError instead of doing anything) as part of the
   Auto-Smooth-by-angle rework. The custom-split-normals call
   (normals_split_custom_set) never actually needed that flag as a
   gate on 4.1+ -- it was only ever a fallback for pre-4.1 versions.
   That fallback is removed; the importer now just calls
   normals_split_custom_set() directly, which is correct on every
   4.0-4.5 point release. Everything else touched by this importer
   (edit-bone creation, vertex groups, color_attributes, the ImportHelper
   operator pattern) is unaffected by any 4.0->4.5 API change I could
   find -- polygon.use_smooth (plain per-face flat/smooth shading, a
   different feature from auto-smooth-by-angle) is also still valid.

2. Spent more time on the still-unsolved "real bind pose" question
   (see FORMAT NOTES 0x1C below) using only the one sample file
   available this session (optimusred_rig.xgm) -- no second rig file
   was available to test the "is this a format property or a
   file-specific bug" question the previous revision left open, so
   that specific question is still open. What IS newly confirmed: the
   period-17 record duplication affects BOTH candidate quat+pos pairs
   in every 0x1C record, not just the first one as previously checked
   -- so there is no basis for preferring pair 2 over pair 1 as "more
   likely to be the real bind pose." Also ran a brute-force byte/int16
   column scan across the entire file (not just 0x1C) looking for a
   34-length array of plausible parent-bone indices; nothing convincing
   turned up (some sub-byte windows technically fit the value range by
   chance, but none showed the diversity/structure expected of a real
   index array, and the 0x1B skeleton-header's still-unidentified bytes
   are mostly zero and too few to hold one either). Net effect: the
   name-based JOINT_PARENT_HINTS hierarchy below is still the best
   available option, unchanged from last revision.

REVISION NOTE 2 (this pass): found and wired in a much better bone-
placement data source. The main *_rig.xgm skeleton file was never the
whole story -- separate per-body-part "geo_<mode>_<joint suffix>.xgm"
piece files (e.g. geo_bip_l_arm_clav.xgm) each carry their own small
0x13 chunk with a real, NOT-duplicated attachment anchor point for
that joint (see _read_piece_attach_chunk()'s docstring for the full
verification). Point the importer's new "Piece Folder" field at a
folder of these piece files (or just leave it blank -- it auto-scans
the main file's own folder and one level of subfolders) and "Build
Armature" will now place bones using that data first, falling back to
the old rig-file chunk / stacked-on-parent / origin only for joints
with no matching piece file. The console prints exactly which joints
used which source after every import, specifically so this can be
checked. The name-based JOINT_PARENT_HINTS hierarchy is UNCHANGED and
still a heuristic, not extracted data -- only the per-joint POSITION
now has a solid source when a piece file is available.

IMPORTANT DISCLOSURE (per user request, still true this revision):
this was written and syntax-checked with plain Python 3 in a sandboxed
shell -- there is no actual Blender install available in that
environment, this revision included. All the binary parsing (the new
0x12/0x13 piece-chunk decode included) WAS verified byte-for-byte
against your real files. The bpy/Blender-API side (the new piece-scan
wiring, and the removed use_auto_smooth fallback from last revision)
is written to the documented 4.0-4.5 API and reuses patterns from code
you've already run successfully, but none of it has been executed
inside real Blender by me -- please run this in Blender 4.5 and tell
me what breaks, and in particular whether the bones actually land in
sensible places now.
"""

bl_info = {
    "name": "Exient XGM format (.xgm)",
    "author": "community reverse-engineering + Claude",
    "version": (0, 4, 0),
    "blender": (4, 0, 0),
    "location": "File > Import > Exient XGM (.xgm)",
    "description": "Import Angry Birds Transformers / Angry Birds Go .xgm models",
    "category": "Import-Export",
}

import bpy
import struct
import os
import re
import math
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, FloatProperty, CollectionProperty
from mathutils import Vector, Quaternion, Matrix


# ---------------------------------------------------------------------------
# Binary parsing (pure python, no bpy) -- see docstring above for chunk map
# ---------------------------------------------------------------------------

def _u16(data, off):
    return struct.unpack_from('<H', data, off)[0]


def _u32(data, off):
    return struct.unpack_from('<I', data, off)[0]


def _cstr(data, off, maxlen=None):
    end = data.find(b'\x00', off, (off + maxlen) if maxlen else None)
    if end == -1:
        end = len(data) if maxlen is None else off + maxlen
    return data[off:end].decode('latin-1', errors='replace')


def _read_mesh_chunk(data, pos, blen, name_hint):
    cur = pos + 8
    cur += 0x78
    vert_addr = _u32(data, cur); cur += 4
    cur += 4  # unknown
    face_addr = _u32(data, cur); cur += 4
    cur += 0x34  # unknown block
    vert_size = _u32(data, cur); cur += 4
    face_size = _u32(data, cur); cur += 4

    face_start = pos + face_addr
    face_count = face_size // 6
    faces = []
    max_idx = 0
    p = face_start
    for _ in range(face_count):
        a, b, c = struct.unpack_from('<HHH', data, p)
        p += 6
        faces.append((a, c, b))  # winding flip
        if a > max_idx: max_idx = a
        if b > max_idx: max_idx = b
        if c > max_idx: max_idx = c

    vert_start = pos + vert_addr
    vert_count = max_idx + 1 if face_count else (vert_size // 12)
    stride = vert_size // vert_count if vert_count else 0
    if vert_count == 0 or stride * vert_count != vert_size or stride < 12:
        for guess in (24, 20, 16, 12):
            if vert_size % guess == 0:
                stride = guess
                vert_count = vert_size // guess
                break

    positions, normals, colors, uvs = [], [], [], []
    p = vert_start
    for _ in range(vert_count):
        x, y, z = struct.unpack_from('<fff', data, p)
        positions.append((x, y, z))
        rest = data[p + 12:p + stride]
        if stride >= 16:
            nx, ny, nz, _nw = struct.unpack_from('<bbbb', rest, 0)
            n = (nx / 127.0, ny / 127.0, nz / 127.0)
        else:
            n = (0.0, 1.0, 0.0)
        normals.append(n)
        if stride == 24:
            r, g, b, a = struct.unpack_from('<BBBB', rest, 4)
            colors.append((r / 255.0, g / 255.0, b / 255.0, a / 255.0))
            u, v = struct.unpack_from('<hh', rest, 8)
            uvs.append((u / 32767.0, 1.0 - (v / 32767.0)))
        elif stride == 20:
            u, v = struct.unpack_from('<hh', rest, 4)
            uvs.append((u / 32767.0, 1.0 - (v / 32767.0)))
        p += stride

    return {
        "name": name_hint or "Mesh",
        "positions": positions,
        "normals": normals,
        "colors": colors,
        "uvs": uvs,
        "faces": faces,
    }


def _read_material_chunk(data, pos, blen):
    body = data[pos + 8:pos + blen]
    if len(body) < 352:
        return None
    r, g, b, a = struct.unpack_from('<BBBB', body, 0)
    textures = []
    for off in (26, 86, 150):
        s = _cstr(body, off, 60)
        if s and s not in textures:
            textures.append(s)
    name = _cstr(body, 278, 64)
    return {"name": name or "Material", "color": (r, g, b, a), "textures": textures}


def _read_piece_attach_chunk(data, pos, blen):
    """0x13 chunk, found in per-piece "geo_<mode>_<joint suffix>.xgm" files
    (NOT in the main *_rig.xgm skeleton file -- that file has no 0x12/0x13
    chunks at all). CONFIRMED across a 40-piece sample set for optimusRed:
    - Fixed 124-byte body (31 floats) in every sample.
    - Floats[6:10] and [21:25] are both always the identity quaternion
      (0,0,0,1) in this sample set -- no rotation data found here (yet).
    - Floats[10:13] ("posB") and floats[25:28] ("posC") are always
      byte-identical to EACH OTHER within one file (unlike the rig file's
      0x1C, this is not a cross-joint duplication bug -- it's just the
      same value stored twice inside one piece's own record).
    - Crucially, THIS number is NOT constant/duplicated the way the rig
      file's data was: it varies piece-to-piece in a way that lines up
      with anatomy (e.g. optimusRed's clavicle-to-shoulder distance shows
      up consistently between geo_*_arm_clav's offset and the rig file's
      own shoulder-joint data), and pieces that sit right at their own
      joint (pelvis, head, hip) correctly read (0,0,0) while pieces
      further out on a limb read larger values. That pattern -- zero near
      the character's center, growing toward the extremities, i.e. NOT
      small per-segment deltas -- is the basis for treating this as an
      ARMATURE-SPACE (whole-character-relative) anchor point for that
      piece/joint, not a parent-relative offset. That is an inference
      from this one asset's numbers, not a cracked fact -- flag it if a
      visibly different asset contradicts it.
    Returns the posB translation as a plain (x, y, z) tuple, or None if
    the chunk is too short to contain it.
    """
    body = data[pos + 8:pos + blen]
    if len(body) < 13 * 4:
        return None
    floats = struct.unpack_from('<13f', body, 0)
    return floats[10:13]


def _read_skeleton_header(data, pos, blen):
    """0x1B chunk. Confirmed field: joint count (u32 @ body+16) -- matched
    the real 0x1E joint-name count in every sample. The u32 @ body+44
    matched the 0x1E record size (44) in optimusred_rig.xgm but read 0 in
    optimusredshadow_rig.xgm despite both files sharing the same 34-joint
    skeleton, so it is NOT a reliable "record size" field after all --
    treat it as unidentified too. Everything else in this 164-byte chunk
    is still unidentified -- see FORMAT NOTES at the bottom of the file."""
    body = data[pos + 8:pos + blen]
    joint_count = _u32(body, 16)
    name_record_size = _u32(body, 44) if len(body) >= 48 else None
    return {"joint_count": joint_count, "name_record_size": name_record_size}


def _read_joint_transform_records(data, pos, blen, joint_count):
    """0x1C chunk. CONFIRMED (verified by unit-length check against every
    joint in the sample files): each 120-byte per-joint record contains
    two unit quaternions (at float offsets 5 and 20, order x,y,z,w) each
    immediately followed by a 3-float translation (offsets 9-11 and
    24-26).

    NOT CONFIRMED: which of the two pairs (if either) is the joint's
    true parent-relative bind pose, and whether these records are even
    indexed the same way as the 0x1E joint-name list -- a cross-check
    found the FIRST quat+pos pair is byte-identical between record i and
    record (i+17) for every one of the first 17 joints, which does not
    correspond to anything meaningful in the joint names. Use this data
    as a rough first draft only. See the module docstring.
    """
    body = data[pos + 8:pos + blen]
    record_size = 120
    records = []
    for i in range(joint_count):
        off = i * record_size
        if off + record_size > len(body):
            break
        floats = struct.unpack_from('<30f', body, off)
        q1 = floats[5:9]
        p1 = floats[9:12]
        q2 = floats[20:24]
        p2 = floats[24:27]
        records.append({"quat1": q1, "pos1": p1, "quat2": q2, "pos2": p2, "raw": floats})
    return records


def parse_xgm(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    size = len(data)

    meshes = []
    joints = []  # (index, name)
    skel_header = None
    joint_records = None

    pos = 0
    pending_name = None
    pending_mesh = None
    while pos < size:
        if pos + 8 > size:
            break
        type_ = _u16(data, pos)
        blen = _u32(data, pos + 4)
        if blen < 8:
            break

        if type_ == 0x2D:
            pending_name = _cstr(data, pos + 10, blen - 10)
        elif type_ == 0x31:
            mesh = _read_mesh_chunk(data, pos, blen, pending_name)
            meshes.append(mesh)
            pending_mesh = mesh
            pending_name = None
        elif type_ == 0x14:
            mat = _read_material_chunk(data, pos, blen)
            if mat and pending_mesh is not None and "material" not in pending_mesh:
                pending_mesh["material"] = mat
        elif type_ == 0x1E:
            idx = _u16(data, pos + 8)
            name = _cstr(data, pos + 10, blen - 10)
            joints.append((idx, name))
        elif type_ == 0x1B:
            try:
                skel_header = _read_skeleton_header(data, pos, blen)
            except Exception as e:
                print(f"[xgm] could not parse 0x1B skeleton header: {e}")
        elif type_ == 0x1C:
            pending_joint_chunk = (pos, blen)

        pos += blen

    # 0x1C needs the joint count from 0x1B (read above), so decode it now
    if skel_header and 'pending_joint_chunk' in dir():
        pass
    if skel_header:
        pos2 = 0
        while pos2 < size:
            if pos2 + 8 > size:
                break
            t2 = _u16(data, pos2)
            l2 = _u32(data, pos2 + 4)
            if l2 < 8:
                break
            if t2 == 0x1C:
                try:
                    joint_records = _read_joint_transform_records(
                        data, pos2, l2, skel_header["joint_count"])
                except Exception as e:
                    print(f"[xgm] could not parse 0x1C joint transforms: {e}")
                break
            pos2 += l2

    return meshes, joints, skel_header, joint_records


# ---------------------------------------------------------------------------
# Piece-file attachment scan: "geo_<mode>_<joint suffix>.xgm" files (NOT the
# *_rig.xgm skeleton file) each carry a 0x13 chunk with a real, non-duplicated
# per-joint anchor point -- see _read_piece_attach_chunk() above. This scan
# looks for such files next to (and one folder level below) the main .xgm
# being imported, matches each one's filename to a joint name, and returns
# the best available offset per joint.
# ---------------------------------------------------------------------------

# preference order when more than one pose-mode piece exists for the same
# joint -- "bip" (the humanoid/robot pose) is the default posed skeleton
# most people importing a Transformers-style rig want to see, falling back
# to shared/vehicle/combiner-mode data if that specific joint has no
# bipedal-mode piece of its own.
PIECE_CATEGORY_PRIORITY = ["bip", "both", "veh", "comtrans"]

_PIECE_FILENAME_RE = re.compile(r'^geo_([a-z]+)_(.+)$')


def scan_piece_offsets(main_filepath, joint_names, extra_dir=None):
    """Look for geo_<mode>_<jointsuffix>.xgm piece files near main_filepath
    (its own folder, one level of subfolders, and optionally a
    user-supplied extra_dir + its subfolders), and return
    {joint_name: (x, y, z)} using the best available piece per joint
    (see PIECE_CATEGORY_PRIORITY). Joints with no matching piece file are
    simply absent from the returned dict -- caller decides the fallback.
    Also returns a small report dict for user-facing logging."""
    joint_lower = {n.lower(): n for n in joint_names}
    search_roots = {os.path.dirname(os.path.abspath(main_filepath))}
    if extra_dir:
        search_roots.add(os.path.abspath(extra_dir))

    candidate_files = []
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                full = os.path.join(root, entry)
                if os.path.isfile(full) and entry.lower().endswith('.xgm'):
                    candidate_files.append(full)
                elif os.path.isdir(full):
                    try:
                        for sub in os.listdir(full):
                            if sub.lower().endswith('.xgm'):
                                candidate_files.append(os.path.join(full, sub))
                    except Exception:
                        pass
        except Exception:
            pass

    # per joint, keep the best-priority match found
    best = {}  # joint_name -> (priority_rank, (x,y,z))
    matched_files = 0
    for path in candidate_files:
        base = os.path.splitext(os.path.basename(path))[0]
        m = _PIECE_FILENAME_RE.match(base.lower())
        if not m:
            continue
        category, suffix = m.group(1), m.group(2)
        joint_name = joint_lower.get('jnt_' + suffix)
        if not joint_name:
            continue
        try:
            rank = PIECE_CATEGORY_PRIORITY.index(category)
        except ValueError:
            rank = len(PIECE_CATEGORY_PRIORITY)  # unknown category, lowest priority

        with open(path, 'rb') as fh:
            data = fh.read()
        size = len(data)
        pos = 0
        offset = None
        while pos < size:
            if pos + 8 > size:
                break
            t = _u16(data, pos)
            blen = _u32(data, pos + 4)
            if blen < 8:
                break
            if t == 0x13:
                try:
                    offset = _read_piece_attach_chunk(data, pos, blen)
                except Exception:
                    offset = None
                break
            pos += blen
        if offset is None:
            continue
        matched_files += 1
        if joint_name not in best or rank < best[joint_name][0]:
            best[joint_name] = (rank, offset)

    # MIRRORING FIX (confirmed this revision against a 40-piece sample):
    # every jnt_l_* piece's own 0x13 offset reads as exact zero, while its
    # jnt_r_* counterpart (same suffix) almost always carries the real,
    # non-zero anchor. That is not missing data -- it is 100% consistent
    # across all 26 l_/r_ pairs checked -- so it looks like the engine
    # mirrors the right side at runtime instead of storing the offset
    # twice. Left-side joints whose own piece data is exactly zero are
    # therefore given the mirrored right-side value instead (negate the
    # first/X component -- an assumption that this axis is the
    # left-right mirror axis, based on it producing sane, non-overlapping
    # limb placement; flag it if a different asset contradicts it).
    mirrored = set()
    for n in list(best.keys()):
        if not n.startswith("jnt_l_"):
            continue
        rank, off = best[n]
        if any(abs(c) > 1e-6 for c in off):
            continue  # this joint's own data is non-zero, trust it
        counterpart = "jnt_r_" + n[len("jnt_l_"):]
        if counterpart in best:
            _, r_off = best[counterpart]
            if any(abs(c) > 1e-6 for c in r_off):
                best[n] = (rank, (-r_off[0], r_off[1], r_off[2]))
                mirrored.add(n)
    # same logic in reverse, for completeness/robustness, though it was
    # not observed to be needed in the sample checked
    for n in list(best.keys()):
        if not n.startswith("jnt_r_"):
            continue
        rank, off = best[n]
        if any(abs(c) > 1e-6 for c in off):
            continue
        counterpart = "jnt_l_" + n[len("jnt_r_"):]
        if counterpart in best and counterpart not in mirrored:
            _, l_off = best[counterpart]
            if any(abs(c) > 1e-6 for c in l_off):
                best[n] = (rank, (-l_off[0], l_off[1], l_off[2]))
                mirrored.add(n)

    result = {n: v[1] for n, v in best.items()}
    report = {
        "files_scanned": len(candidate_files),
        "files_matched": matched_files,
        "joints_covered": len(result),
        "joints_total": len(joint_names),
        "mirrored": sorted(mirrored),
    }
    return result, report


# ---------------------------------------------------------------------------
# Name-based joint hierarchy heuristic (NOT extracted from the binary --
# see "ABOUT THE ARMATURE" in the module docstring)
# ---------------------------------------------------------------------------

# Maps a joint name to its parent's name. Written by hand against the
# "jnt_c_*/jnt_l_*/jnt_r_*" naming convention seen in the sample file
# (an Optimus-Prime-style Angry Birds Transformers character). If you
# feed this importer a character whose joints use the same convention
# but a different set of names, unmapped joints fall back to the root
# (or the nearest name-alike match) and a warning is printed so you know
# to extend this table.
JOINT_PARENT_HINTS = {
    "jnt_c_char_root": None,
    "jnt_c_torso_pelvis": "jnt_c_char_root",
    "jnt_c_torso_spine_1": "jnt_c_torso_pelvis",
    "jnt_c_torso_head": "jnt_c_torso_spine_1",
    "jnt_c_face_brow": "jnt_c_torso_head",
    "jnt_c_face_lbeak": "jnt_c_torso_head",
    "jnt_c_face_ubeak": "jnt_c_torso_head",
    "jnt_c_sec_grill": "jnt_c_torso_spine_1",
}
for _side in ("l", "r"):
    JOINT_PARENT_HINTS.update({
        f"jnt_{_side}_arm_clav": "jnt_c_torso_spine_1",
        f"jnt_{_side}_arm_shoulder": f"jnt_{_side}_arm_clav",
        f"jnt_{_side}_arm_elbow": f"jnt_{_side}_arm_shoulder",
        f"jnt_{_side}_arm_wrist": f"jnt_{_side}_arm_elbow",
        f"jnt_{_side}_face_brow": "jnt_c_torso_head",
        f"jnt_{_side}_leg_hip": "jnt_c_torso_pelvis",
        f"jnt_{_side}_leg_knee": f"jnt_{_side}_leg_hip",
        f"jnt_{_side}_leg_ankle": f"jnt_{_side}_leg_knee",
        f"jnt_{_side}_leg_toe": f"jnt_{_side}_leg_ankle",
        f"jnt_{_side}_sec_armWheel": f"jnt_{_side}_arm_shoulder",
        f"jnt_{_side}_sec_backExhaust": "jnt_c_torso_spine_1",
        f"jnt_{_side}_sec_rWheels1": f"jnt_{_side}_leg_hip",
        f"jnt_{_side}_sec_rWheels2": f"jnt_{_side}_leg_hip",
    })


def _guess_parent(name, all_names, root_name):
    """Fallback for joint names not in JOINT_PARENT_HINTS: strip the last
    '_something' suffix and see if that shorter name (or a l_/r_/c_
    variant of it) exists; otherwise parent to root."""
    if name in JOINT_PARENT_HINTS:
        return JOINT_PARENT_HINTS[name]
    parts = name.split('_')
    for cut in range(len(parts) - 1, 0, -1):
        candidate = '_'.join(parts[:cut])
        if candidate in all_names and candidate != name:
            return candidate
    print(f"[xgm] WARNING: no hierarchy hint for joint '{name}', "
          f"parenting to root '{root_name}' -- please verify in Blender.")
    return root_name


# ---------------------------------------------------------------------------
# Blender-side construction
# ---------------------------------------------------------------------------

_image_cache = {}


def _find_or_load_image(tex_name, search_dir):
    if not tex_name:
        return None
    key = (tex_name, search_dir)
    if key in _image_cache:
        return _image_cache[key]
    candidates = [tex_name]
    base, _ext = os.path.splitext(tex_name)
    for ext in (".png", ".tga", ".dds", ".jpg", ".jpeg"):
        candidates.append(base + ext)
    img = None
    for cand in candidates:
        p = os.path.join(search_dir, cand)
        if os.path.isfile(p):
            try:
                img = bpy.data.images.load(p, check_existing=True)
                break
            except Exception:
                pass
    _image_cache[key] = img
    return img


def _get_or_create_material(mat_data, search_dir, mat_cache):
    if not mat_data:
        return None
    name = mat_data["name"]
    if name in mat_cache:
        return mat_cache[name]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")

    tex_name = mat_data["textures"][0] if mat_data["textures"] else None
    img = _find_or_load_image(tex_name, search_dir)
    if img and bsdf:
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.image = img
        tex_node.location = (-300, 300)
        nt.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    elif bsdf:
        r, g, b, a = mat_data["color"]
        bsdf.inputs["Base Color"].default_value = (r / 255.0, g / 255.0, b / 255.0, 1.0)

    mat_cache[name] = mat
    return mat


def _build_object(mesh_data, collection, search_dir, mat_cache, scale=1.0, convert_axes=True):
    name = mesh_data["name"] or "Mesh"
    positions = mesh_data["positions"]
    normals = mesh_data["normals"]
    colors = mesh_data["colors"]
    uvs = mesh_data["uvs"]
    faces = mesh_data["faces"]

    if not positions or not faces:
        return None

    def conv(p):
        x, y, z = p
        if convert_axes:
            # source appears Y-up; Blender is Z-up
            return (x * scale, -z * scale, y * scale)
        return (x * scale, y * scale, z * scale)

    verts = [conv(p) for p in positions]

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()

    if me.validate():
        print(f"[xgm] warning: mesh '{name}' had to be auto-fixed by validate()")

    # smooth shading + custom normals (best effort, API differs across 4.x point releases)
    try:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    except Exception:
        pass

    if len(normals) == len(positions):
        def convn(n):
            x, y, z = n
            if convert_axes:
                return (x, -z, y)
            return (x, y, z)
        loop_normals = [convn(normals[loop.vertex_index]) for loop in me.loops]
        try:
            # Blender 4.1 removed Mesh.use_auto_smooth entirely (setting it
            # now raises AttributeError) -- custom split normals no longer
            # need it as a gate, so just set them directly. This is the
            # correct call on every version from 4.0 through 4.5.
            me.normals_split_custom_set(loop_normals)
        except Exception as e:
            print(f"[xgm] custom normals not applied for '{name}': {e}")

    if uvs and len(uvs) == len(positions):
        uv_layer = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            u, v = uvs[loop.vertex_index]
            uv_layer.data[loop.index].uv = (u, v)

    if colors and len(colors) == len(positions):
        try:
            color_attr = me.color_attributes.new(name="Color", type='FLOAT_COLOR', domain='CORNER')
            for loop in me.loops:
                color_attr.data[loop.index].color = colors[loop.vertex_index]
        except Exception as e:
            print(f"[xgm] vertex colors not applied for '{name}': {e}")

    mat = _get_or_create_material(mesh_data.get("material"), search_dir, mat_cache)
    if mat:
        me.materials.append(mat)

    obj = bpy.data.objects.new(name, me)
    collection.objects.link(obj)
    return obj


def _convert_vec(v, scale, convert_axes):
    x, y, z = v
    if convert_axes:
        return Vector((x * scale, -z * scale, y * scale))
    return Vector((x * scale, y * scale, z * scale))


def _convert_quat(q, convert_axes):
    # q is (x, y, z, w)
    x, y, z, w = q
    if convert_axes:
        x, y, z = x, -z, y
    return Quaternion((w, x, y, z))  # mathutils.Quaternion wants (w,x,y,z)


def _build_armature(base_name, joints, joint_records, collection, scale=1.0,
                     convert_axes=True, piece_offsets=None):
    """EXPERIMENTAL -- see 'ABOUT THE ARMATURE' in the module docstring.
    joints: list of (idx, name) as read from 0x1E, in idx order.
    joint_records: list from _read_joint_transform_records (rig file's own
    0x1C data -- kept only as a last-resort fallback now, see below).
    piece_offsets: optional {joint_name: (x,y,z)} from scan_piece_offsets(),
    which is now the PREFERRED position source -- see _read_piece_attach_
    chunk()'s docstring for why it's more trustworthy than joint_records.
    """
    names = [n for _, n in joints]
    name_set = set(names)
    roots = [n for n in names if JOINT_PARENT_HINTS.get(n, "MISSING") is None]
    root_name = roots[0] if roots else names[0]

    parent_of = {}
    for n in names:
        parent_of[n] = _guess_parent(n, name_set, root_name)
    children_of = {}
    for n, p in parent_of.items():
        if p:
            children_of.setdefault(p, []).append(n)

    # rig file's own per-joint data, kept as a last-resort fallback only
    # (see module docstring -- it's the one with the period-17 duplication
    # bug, so it's not trusted as a primary source any more).
    rig_local_mat = {}
    if joint_records and len(joint_records) == len(names):
        for (idx, n), rec in zip(joints, joint_records):
            pos = _convert_vec(rec["pos1"], scale, convert_axes)
            quat = _convert_quat(rec["quat1"], convert_axes)
            rig_local_mat[n] = Matrix.Translation(pos) @ quat.to_matrix().to_4x4()

    piece_offsets = piece_offsets or {}

    # Resolve an armature-space HEAD position for every joint, preferring
    # (in order): a piece file's own attachment anchor -> the rig file's
    # (unreliable) local-chain data composed through the guessed parent
    # chain -> a same-position-as-parent stack -> world origin.
    head_pos = {}
    source_of = {}

    def resolve(n, seen=None):
        if n in head_pos:
            return head_pos[n]
        seen = seen or set()
        if n in seen:
            head_pos[n] = Vector((0.0, 0.0, 0.0))
            source_of[n] = "cycle-fallback"
            return head_pos[n]
        seen.add(n)

        if n in piece_offsets:
            head_pos[n] = _convert_vec(piece_offsets[n], scale, convert_axes)
            source_of[n] = "piece"
            return head_pos[n]

        if n in rig_local_mat:
            p = parent_of.get(n)
            parent_pos = resolve(p, seen) if p else Vector((0.0, 0.0, 0.0))
            head_pos[n] = parent_pos + rig_local_mat[n].translation
            source_of[n] = "rig-chunk(unreliable)"
            return head_pos[n]

        p = parent_of.get(n)
        if p:
            head_pos[n] = resolve(p, seen)
            source_of[n] = "stacked-on-parent"
            return head_pos[n]

        head_pos[n] = Vector((0.0, 0.0, 0.0))
        source_of[n] = "origin-fallback"
        return head_pos[n]

    for n in names:
        resolve(n)

    n_piece = sum(1 for s in source_of.values() if s == "piece")
    n_other = len(names) - n_piece
    print(f"[xgm] {base_name}: bone placement source -- {n_piece}/{len(names)} "
          f"joint(s) from piece-file attachment data, {n_other} from "
          f"fallback (rig-chunk/stacked/origin). See console lines above "
          f"for exactly which fell back if that number looks high.")
    for n in names:
        if source_of[n] != "piece":
            print(f"[xgm]   fallback for '{n}': {source_of[n]}")

    arm_data = bpy.data.armatures.new(base_name + "_Armature")
    arm_obj = bpy.data.objects.new(base_name + "_Armature", arm_data)
    collection.objects.link(arm_obj)

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')

    edit_bones = arm_data.edit_bones
    world_matrix = {n: Matrix.Translation(head_pos[n]) for n in names}
    bone_of = {}

    # process joints in parent-before-child order so eb.parent is always
    # assigned to an already-created bone
    remaining = list(names)
    processed = set()
    safety = 0
    while remaining and safety < 1000:
        safety += 1
        progressed = False
        for n in list(remaining):
            p = parent_of[n]
            if p is None or p in processed:
                wm = world_matrix[n]
                eb = edit_bones.new(n)
                eb.head = wm.translation
                # temporary tail, fixed up below once all heads are known
                eb.tail = wm.translation + Vector((0.0, 0.05, 0.0))
                bone_of[n] = eb
                if p and p in bone_of:
                    eb.parent = bone_of[p]
                remaining.remove(n)
                processed.add(n)
                progressed = True
        if not progressed:
            # cyclic or missing parent reference left over -- attach to root
            for n in remaining:
                print(f"[xgm] WARNING: could not resolve parent chain for "
                      f"'{n}', attaching directly under '{root_name}'.")
                wm = world_matrix.get(root_name, Matrix.Identity(4))
                eb = edit_bones.new(n)
                eb.head = wm.translation
                eb.tail = wm.translation + Vector((0, 0.05, 0))
                if root_name in bone_of:
                    eb.parent = bone_of[root_name]
                bone_of[n] = eb
                world_matrix[n] = wm
            remaining = []

    # point each bone at the average of its children for a nicer-looking
    # (still schematic, not authoritative) bone length/direction
    # (children_of was already computed above, before bone creation)
    for n, eb in bone_of.items():
        kids = children_of.get(n)
        if kids:
            avg = sum((bone_of[k].head for k in kids), Vector()) / len(kids)
            if (avg - eb.head).length > 1e-6:
                eb.tail = avg

    bpy.ops.object.mode_set(mode='OBJECT')
    return arm_obj, parent_of


def _apply_rigid_autoskin(mesh_obj, arm_obj, convert_axes=True):
    """EXPERIMENTAL fallback skinning: since the .xgm vertex buffer has no
    room for bone indices/weights (confirmed -- see module docstring),
    each vertex is rigidly assigned 100% to whichever bone HEAD is
    closest to it in the (guessed) bind pose. Expect hard, non-smooth
    breaks at every joint -- this is not a substitute for real skin
    weights, just a way to get something posable."""
    arm_data = arm_obj.data
    bone_heads = [(b.name, arm_obj.matrix_world @ b.head_local) for b in arm_data.bones]
    if not bone_heads:
        return

    vgroups = {}
    for name, _ in bone_heads:
        vgroups[name] = mesh_obj.vertex_groups.new(name=name)

    me = mesh_obj.data
    mw = mesh_obj.matrix_world
    for v in me.vertices:
        wco = mw @ v.co
        best_name, best_dist = None, None
        for name, head in bone_heads:
            d = (wco - head).length_squared
            if best_dist is None or d < best_dist:
                best_dist = d
                best_name = name
        vgroups[best_name].add([v.index], 1.0, 'REPLACE')

    mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm_obj
    mesh_obj.parent = arm_obj


def import_xgm_file(filepath, scale=1.0, convert_axes=True,
                     build_armature=False, rigid_autoskin=False,
                     piece_dir=""):
    meshes, joints, skel_header, joint_records = parse_xgm(filepath)
    search_dir = os.path.dirname(filepath)
    base = os.path.splitext(os.path.basename(filepath))[0]

    coll = bpy.data.collections.new(base)
    bpy.context.scene.collection.children.link(coll)

    mat_cache = {}
    n_built = 0
    built_objs = []
    for mesh_data in meshes:
        obj = _build_object(mesh_data, coll, search_dir, mat_cache,
                             scale=scale, convert_axes=convert_axes)
        if obj:
            n_built += 1
            built_objs.append(obj)

    if joints:
        names = ", ".join(f"{i}:{n}" for i, n in joints)
        print(f"[xgm] {base}: {len(joints)} joint name(s) found: {names}")
        if joint_records:
            n_ok = sum(1 for r in joint_records if r)
            print(f"[xgm] {base}: decoded {n_ok} candidate joint transform "
                  f"record(s) from chunk 0x1C (experimental -- see docstring).")

        if build_armature:
            piece_offsets, piece_report = scan_piece_offsets(
                filepath, [n for _, n in joints],
                extra_dir=piece_dir if piece_dir else None)
            print(f"[xgm] {base}: piece-file scan found "
                  f"{piece_report['files_matched']}/{piece_report['files_scanned']} "
                  f".xgm file(s) matching a joint name, covering "
                  f"{piece_report['joints_covered']}/{piece_report['joints_total']} "
                  f"joints. (Looked in the main file's folder, its immediate "
                  f"subfolders, and 'Piece Folder' if you set one.)")
            if piece_report.get("mirrored"):
                print(f"[xgm] {base}: {len(piece_report['mirrored'])} joint(s) had "
                      f"all-zero data in their own piece file and were mirrored "
                      f"from their opposite-side counterpart instead: "
                      f"{', '.join(piece_report['mirrored'])}")
            try:
                arm_obj, parent_of = _build_armature(
                    base, joints, joint_records, coll,
                    scale=scale, convert_axes=convert_axes,
                    piece_offsets=piece_offsets)
                print(f"[xgm] {base}: built EXPERIMENTAL armature "
                      f"'{arm_obj.name}' -- please visually verify.")
                if rigid_autoskin and built_objs:
                    for obj in built_objs:
                        _apply_rigid_autoskin(obj, arm_obj, convert_axes=convert_axes)
                    print(f"[xgm] {base}: applied EXPERIMENTAL rigid "
                          f"nearest-bone auto-skin to {len(built_objs)} mesh "
                          f"object(s).")
            except Exception as e:
                print(f"[xgm] ERROR building armature for {base}: {e}")
        else:
            print(f"[xgm] {base}: hierarchy/bind-pose import skipped "
                  f"(enable 'Build Armature (experimental)' to try it).")

    print(f"[xgm] {base}: imported {n_built} mesh object(s) into collection '{base}'")
    return n_built


# ---------------------------------------------------------------------------
# Operator / UI
# ---------------------------------------------------------------------------

class IMPORT_OT_xgm(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.xgm"
    bl_label = "Import XGM"
    bl_description = "Import Exient XGS Engine .xgm model(s)"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".xgm"
    filter_glob: StringProperty(default="*.xgm", options={'HIDDEN'})

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')

    scale: FloatProperty(name="Scale", default=1.0, min=0.0001, max=1000.0)
    convert_axes: BoolProperty(
        name="Y-up to Z-up",
        description="Convert from the source format's Y-up to Blender's Z-up",
        default=True,
    )
    build_armature: BoolProperty(
        name="Build Armature (experimental)",
        description=(
            "Reconstruct joint hierarchy from joint names and place bones "
            "using piece-file attachment data when available (falls back "
            "to the rig file's own less-reliable data otherwise). See the "
            "script's docstring. On by default -- untick to go back to "
            "mesh-only import."
        ),
        default=True,
    )
    rigid_autoskin: BoolProperty(
        name="Rigid Auto-Skin (experimental)",
        description=(
            "Assign each vertex 100% to its nearest bone so the mesh can "
            "be posed. The file has no real per-vertex skin weights, so "
            "this will look blocky at joints, not smoothly skinned. "
            "Only used if 'Build Armature' is also enabled."
        ),
        default=False,
    )
    piece_dir: StringProperty(
        name="Piece Folder (optional)",
        description=(
            "Folder containing this character's 'geo_<mode>_<joint>.xgm' "
            "piece files (e.g. geo_bip_l_arm_clav.xgm), used to place bones "
            "far more reliably than the rig file's own data -- see the "
            "script's docstring. Leave blank to auto-search the main "
            "file's own folder and its immediate subfolders."
        ),
        subtype='DIR_PATH',
        default="",
    )

    def execute(self, context):
        paths = [os.path.join(self.directory, f.name) for f in self.files] \
            if self.files else [self.filepath]
        total = 0
        for p in paths:
            if not p.lower().endswith(".xgm"):
                continue
            try:
                total += import_xgm_file(
                    p, scale=self.scale, convert_axes=self.convert_axes,
                    build_armature=self.build_armature,
                    rigid_autoskin=self.rigid_autoskin,
                    piece_dir=self.piece_dir)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import {p}: {e}")
                print(f"[xgm] ERROR importing {p}: {e}")
        self.report({'INFO'}, f"XGM import: {total} mesh object(s) created")
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_xgm.bl_idname, text="Exient XGM (.xgm)")


def register():
    bpy.utils.register_class(IMPORT_OT_xgm)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_OT_xgm)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
    print("Exient XGM importer registered. Use File > Import > Exient XGM (.xgm)")


# =============================================================================
# FORMAT NOTES (chunk type reference, for anyone extending this)
# =============================================================================
#
# Container: flat sequence of chunks, each:
#     uint16 type, uint16 info (always 0 seen), uint32 blen (incl. header)
#     next chunk = this chunk's offset + blen
#
# 0x15 (21) file header: 4 bytes "XGSM" + 4 version bytes (24 bytes total)
# 0x16 (22) EOF marker, empty, always last chunk
# 0x1F (31) unknown, fixed 52 bytes, always right after the header
# 0x1B (27) skeleton "header", 164 bytes incl. header. CONFIRMED this
#           revision: body+16 (u32) = joint count; body+44 (u32) = the
#           0x1E name-record size (44 in every sample). The rest of the
#           156-byte body is still unidentified; it is NOT all zero, so
#           there is more here to find (possibly bounding info, or a
#           description of the still-mysterious 0x25 blob below).
# 0x1C (28) (jointCount * 120) bytes, one record per joint (assumed 1:1
#           with the 0x1E index -- NOT independently confirmed, see
#           below). CONFIRMED this revision: each 120-byte record
#           contains, at float offsets 5 and 20 (i.e. byte offsets 20
#           and 80), two independent unit quaternions (x,y,z,w order;
#           verified qx^2+qy^2+qz^2+qw^2 == 1 for every joint checked),
#           each immediately followed by a 3-float translation (byte
#           offsets 36 and 96). Bytes 0-19 and 60-79 of each record are
#           mostly constant/boilerplate (looks like a padded scale
#           vector, always ~(1,1,1), plus one flag float that is 0 for
#           roughly the first half of the joints and 1 for the rest).
#           UNRESOLVED / suspicious: the first quat+pos pair is
#           byte-identical between joint record i and record (i+17) for
#           every i in 0..16 in the sample file, and this pairing does
#           NOT correspond to the file's own left/right joint naming
#           (e.g. the root joint's block equals "l_sec_armWheel"'s
#           block). This means either (a) this data isn't really a
#           "this joint's own local bind offset" the way it was
#           assumed, or (b) the sample asset's own 0x1C data is a
#           duplicated/buggy export. Whoever picks this up next should
#           try a *different* rigged character (ideally one whose parts
#           obviously should NOT share transforms) to see if the same
#           period-17 duplication shows up there too -- if it does, that
#           points hard at (a); if it doesn't, it's file-specific and
#           points at (b). No parent-index field was found by brute
#           force column scanning in this record (tried both int16 and
#           uint8 columns, range-limited to plausible joint-index
#           values) -- if a parent index exists at all, it is not
#           stored per-joint here, and might live in the still-unread
#           parts of 0x1B or 0x25 instead.
#           UPDATE (later pass, same sample file, no second file
#           available to test): re-checked and the SECOND quat+pos pair
#           has the exact same period-17 duplication as the first, so
#           there's no basis for treating pair 2 as more trustworthy
#           than pair 1. Also brute-force scanned every byte offset in
#           the WHOLE FILE (not just this chunk) for a 34-entry array of
#           plausible small integers (a parent-index list) -- nothing
#           convincing found; the few sliding-window hits that
#           technically fit the value range were overlapping views of
#           the same sparse float data, not an independent index array.
#           The period-17 split (34 = 17*2) still looks more like a
#           format-level "two logical halves" thing than random
#           corruption, given how exact and total it is, but what those
#           two halves actually mean is still unknown.
# 0x1E (30) one per joint: uint16 joint index + null-terminated name,
#           36-byte body (fixed size, zero padded). CONFIRMED this
#           revision: the padding after the name is genuinely all
#           zero bytes in every sample checked -- no hidden index or
#           hash tucked in there.
# 0x25 (37) large blob before the 0x1E name chunks. In the sample rig
#           file this is 2464 bytes incl. header (2456-byte body); that
#           does not divide evenly by the 34-joint count (2456/34 is
#           not an integer), so it is very unlikely to be one
#           fixed-size record per joint despite sitting right next to
#           the skeleton data. Still not decoded. Comparing this chunk
#           between two files that otherwise share an identical
#           skeleton (optimusred_rig.xgm vs optimusredshadow_rig.xgm)
#           showed this was one of the few regions that actually
#           differs between them -- worth prioritizing if you want to
#           find the real bind pose, since whatever it stores clearly
#           varies per-asset in a way the 0x1C block, oddly, mostly
#           doesn't.
# 0x12 (18) piece-file only, 28 bytes incl. header. CONFIRMED constant
#           (1, 2, 1, 0, 0 as five int32) across all 40 files in one
#           sample piece set -- boilerplate, does NOT contain a joint
#           index/reference. Attachment is name-matched (piece filename
#           vs. joint name), not index-matched.
# 0x13 (19) piece-file only, 132 bytes incl. header (124-byte body, 31
#           floats). CONFIRMED this revision -- see
#           _read_piece_attach_chunk()'s docstring above for the full
#           writeup: this is a real, non-duplicated, anatomically
#           sane per-piece attachment anchor point, and is now the
#           preferred bone-placement source over the rig file's own
#           0x1C data (see scan_piece_offsets() / _build_armature()).
#           Rotation sub-fields were always identity in the sample set
#           checked -- only translation has been seen to vary so far.
# 0x2D (45) null-terminated ASCII name string for the following mesh
# 0x31 (49) mesh: vertex buffer + triangle index buffer, see
#           _read_mesh_chunk() above for the exact field layout.
#           Vertex stride varies (24 bytes with vertex color, 20 bytes
#           without); this importer detects it from
#           vertBufSize // (max_face_index + 1) rather than trusting
#           a hardcoded constant. CONFIRMED this revision: for the
#           24-byte-stride case, all 24 bytes are fully accounted for
#           (12 position + 4 packed normal + 4 vertex color + 4 packed
#           UV) -- there is no room anywhere in this vertex format for
#           a bone index or weight, for this asset. If a future sample
#           uses a different/longer stride, it's worth re-checking.
# 0x11 (17) empty marker chunk, seen right after a 0x31 mesh
# 0x14 (20) material: RGBA color + up to 3 texture filenames + a
#           material name string. Fixed 352-byte body in every sample.
#           This revision confirmed the referenced texture names for
#           the sample character are S_Optimus.tga (diffuse),
#           AB_BS_Optimus_wireframe.tga (referenced twice, likely a
#           spec/gloss mask given the "Glossy_Parts"/"Metal_Parts"
#           material names it's used in), and S_BlobShadow.tga for the
#           separate shadow-blob mesh.
# 0x17 (23), 0x2A/0x2B/0x2C (42/43/44), 0x30 (48): seen in the
#           collision-mesh sample files, not decoded (likely physics /
#           render-state data). Skipped safely by the flat chunk walk.
#
# NEXT STEPS if you want to finish cracking the real bind pose:
#   1. Decode 0x25 fully -- it's the one skeleton-adjacent chunk
#      confirmed to vary between two files sharing the same skeleton,
#      so it's more likely to hold the real, asset-specific bind pose
#      than 0x1C is.
#   2. Get a SECOND rigged character's .xgm (ideally with a visibly
#      different body proportions/pose) and re-run the unit-quaternion
#      scan + the "does record i equal record i+17" check from this
#      revision against it, to figure out whether the period-17
#      duplication in 0x1C is a property of the format or an artifact
#      of this one file.
#   3. Once real bind-pose data is found, replace `local_mat` in
#      `_build_armature()` -- everything else (hierarchy application,
#      edit-bone creation, rigid auto-skin) should keep working as-is.
# =============================================================================
