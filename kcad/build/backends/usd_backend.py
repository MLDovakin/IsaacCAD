"""USD / Isaac Sim backend.

Import of pxr is deferred so that everything else in the toolkit (specs, invariants,
golden diffs, CI) runs in a plain Python environment. Run this one inside Isaac Sim's
python or any environment with usd-core + (optionally) omni.physx schemas.

Layering: geometry is authored into its own sublayer so that 'nuke and rebuild' never
takes lights, cameras and render settings with it, and every rebuild stays reversible.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ...util.vecmath import Mat4

_PXR_HINT = (
    "pxr (USD) is not importable. Run this inside Isaac Sim's python "
    "(./python.sh) or `pip install usd-core` for geometry-only authoring."
)


def _pxr():
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(_PXR_HINT) from exc
    return Gf, Sdf, Usd, UsdGeom, UsdPhysics


class UsdBackend:
    name = "usd"

    def __init__(self, stage_path: str | None = None, geometry_layer: str | None = None):
        self.stage_path = stage_path
        self.geometry_layer = geometry_layer
        self.stage = None
        self._Gf = self._Sdf = self._Usd = self._UsdGeom = self._UsdPhysics = None

    # ------------------------------------------------------------------ stage
    def open_stage(self, spec, layer: str | None = None) -> None:
        Gf, Sdf, Usd, UsdGeom, UsdPhysics = _pxr()
        self._Gf, self._Sdf, self._Usd = Gf, Sdf, Usd
        self._UsdGeom, self._UsdPhysics = UsdGeom, UsdPhysics

        if self.stage_path:
            self.stage = Usd.Stage.Open(self.stage_path) if _exists(self.stage_path) \
                else Usd.Stage.CreateNew(self.stage_path)
        else:
            self.stage = Usd.Stage.CreateInMemory()

        UsdGeom.SetStageUpAxis(self.stage, UsdGeom.Tokens.z if spec.up_axis == "Z"
                               else UsdGeom.Tokens.y)
        UsdGeom.SetStageMetersPerUnit(self.stage, float(spec.meters_per_unit))

        target = layer or self.geometry_layer
        if target:
            sub = Sdf.Layer.FindOrOpen(target) or Sdf.Layer.CreateNew(target)
            root = self.stage.GetRootLayer()
            if sub.identifier not in root.subLayerPaths:
                root.subLayerPaths.append(sub.identifier)
            self.stage.SetEditTarget(self._Usd.EditTarget(sub))

    def clear(self, root: str) -> None:
        if self.stage.GetPrimAtPath(root):
            self.stage.RemovePrim(root)

    # ------------------------------------------------------------------ prims
    def _set_world(self, prim, world: Mat4) -> None:
        Gf, UsdGeom = self._Gf, self._UsdGeom
        x = UsdGeom.Xformable(prim)
        x.ClearXformOpOrder()
        m = Gf.Matrix4d(*[float(v) for v in np.asarray(world).T.reshape(-1)])
        x.AddTransformOp().Set(m)

    def create_xform(self, prim_path: str, world: Mat4, note: str = "") -> None:
        prim = self._UsdGeom.Xform.Define(self.stage, prim_path).GetPrim()
        self._set_world(prim, world)
        if note:
            prim.SetCustomDataByKey("kcad:note", note)

    def create_prim(self, prim_path: str, kind: str, size: dict[str, float],
                    world: Mat4, opts: dict[str, Any]) -> None:
        UsdGeom, UsdPhysics = self._UsdGeom, self._UsdPhysics
        if kind == "box":
            g = UsdGeom.Cube.Define(self.stage, prim_path)
            g.GetSizeAttr().Set(1.0)
            g.AddScaleOp()  # replaced by transform below; kept for clarity
            world = np.asarray(world) @ _scale_matrix(size["x"], size["y"], size["z"])
        elif kind in ("cylinder", "capsule"):
            g = (UsdGeom.Cylinder if kind == "cylinder" else UsdGeom.Capsule).Define(
                self.stage, prim_path)
            g.GetRadiusAttr().Set(float(size["radius"]))
            g.GetHeightAttr().Set(float(size["height"]))
            g.GetAxisAttr().Set(opts.get("axis", "Z"))
        elif kind == "sphere":
            g = UsdGeom.Sphere.Define(self.stage, prim_path)
            g.GetRadiusAttr().Set(float(size["radius"]))
        elif kind == "plane":
            g = UsdGeom.Cube.Define(self.stage, prim_path)
            g.GetSizeAttr().Set(1.0)
            world = np.asarray(world) @ _scale_matrix(size["x"], size["y"], 1e-3)
        elif kind == "mesh":
            g = UsdGeom.Xform.Define(self.stage, prim_path)
            g.GetPrim().GetReferences().AddReference(opts["mesh"])
        else:
            g = UsdGeom.Xform.Define(self.stage, prim_path)

        prim = g.GetPrim()
        self._set_world(prim, world)

        physics = opts.get("physics", "static")
        if opts.get("collision", True) and physics != "visual":
            UsdPhysics.CollisionAPI.Apply(prim)
        if physics == "rigid":
            UsdPhysics.RigidBodyAPI.Apply(prim)
            if opts.get("mass"):
                UsdPhysics.MassAPI.Apply(prim).GetMassAttr().Set(float(opts["mass"]))
        elif physics == "kinematic":
            rb = UsdPhysics.RigidBodyAPI.Apply(prim)
            rb.GetKinematicEnabledAttr().Set(True)

    def create_camera(self, prim_path: str, world: Mat4, opts: dict[str, Any]) -> None:
        cam = self._UsdGeom.Camera.Define(self.stage, prim_path)
        if opts.get("orthographic"):
            cam.GetProjectionAttr().Set("orthographic")
            cam.GetHorizontalApertureAttr().Set(float(opts.get("aperture_mm", 500.0)))
            cam.GetVerticalApertureAttr().Set(float(opts.get("aperture_v_mm",
                                                             opts.get("aperture_mm", 500.0))))
        else:
            cam.GetFocalLengthAttr().Set(float(opts.get("focal_mm", 24.0)))
            cam.GetHorizontalApertureAttr().Set(float(opts.get("aperture_mm", 20.955)))
        self._set_world(cam.GetPrim(), world)

    # ----------------------------------------------------------------- joints
    def create_joint(self, prim_path: str, kind: str, parent_path: str, child_path: str,
                     axis, anchor, limits, drive: dict[str, Any]) -> None:
        Gf, UsdPhysics = self._Gf, self._UsdPhysics
        table = {
            "fixed": UsdPhysics.FixedJoint,
            "revolute": UsdPhysics.RevoluteJoint,
            "prismatic": UsdPhysics.PrismaticJoint,
            "spherical": UsdPhysics.SphericalJoint,
        }
        if kind == "free":
            return
        j = table[kind].Define(self.stage, prim_path)
        if parent_path and parent_path != "world":
            j.GetBody0Rel().SetTargets([parent_path])
        j.GetBody1Rel().SetTargets([child_path])

        if kind in ("revolute", "prismatic"):
            j.GetAxisAttr().Set(_dominant_axis(axis))
            if limits is not None:
                j.GetLowerLimitAttr().Set(float(limits[0]))
                j.GetUpperLimitAttr().Set(float(limits[1]))
        if anchor is not None:
            j.GetLocalPos0Attr().Set(Gf.Vec3f(*[float(v) for v in anchor]))

        if drive:
            from pxr import UsdPhysics as _UP
            api = _UP.DriveAPI.Apply(j.GetPrim(),
                                     "angular" if kind == "revolute" else "linear")
            if "target_position" in drive:
                api.GetTargetPositionAttr().Set(float(drive["target_position"]))
            if "target_velocity" in drive:
                api.GetTargetVelocityAttr().Set(float(drive["target_velocity"]))
            api.GetStiffnessAttr().Set(float(drive.get("stiffness", 0.0)))
            api.GetDampingAttr().Set(float(drive.get("damping", 1e4)))
            api.GetMaxForceAttr().Set(float(drive.get("max_force", 1e6)))

    # ------------------------------------------------------------------- misc
    def save(self, path: str | None = None) -> str | None:
        if path:
            self.stage.Export(path)
            return path
        if self.stage_path:
            self.stage.Save()
            return self.stage_path
        return None

    def dump(self) -> dict[str, Any]:
        raise NotImplementedError("use kcad.io.inspect_stage.dump_usd_stage(stage)")
        


def _scale_matrix(sx: float, sy: float, sz: float) -> np.ndarray:
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = float(sx), float(sy), float(sz)
    return m


def _dominant_axis(axis) -> str:
    a = np.abs(np.asarray(axis, dtype=float))
    return "XYZ"[int(np.argmax(a))]


def _exists(p: str) -> bool:
    from pathlib import Path
    return Path(p).exists()
