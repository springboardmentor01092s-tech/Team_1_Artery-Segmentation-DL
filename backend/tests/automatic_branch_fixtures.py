"""Analytic world-space fixtures, independently evaluated without inverse affine."""
import numpy as np
from app.schemas.stenosis import VolumeGeometry
from app.services.experimental_candidates import mask_identity
from app.services.stenosis_geometry import geometry_fingerprint

CONFIGURATIONS = [
    ("off_center", "axis", (1., 1., 1.), 0., (0., 0., 0.)),
    ("diagonal", "diagonal", (1., 1., 1.), 0., (0., 0., 0.)),
    ("curved", "curved", (1., 1., 1.), 0., (0., 0., 0.)),
    ("anisotropic_diagonal", "diagonal", (.7, 1., 1.3), 0., (.2, .35, .1)),
    ("anisotropic_curved", "curved", (.7, 1., 1.3), 0., (.2, .35, .1)),
    ("oblique_grid", "diagonal", (1., 1., 1.), .43, (.25, .25, .25)),
    ("fine_diagonal", "diagonal", (.75, .75, .75), 0., (.5, .5, .5)),
    ("coarse_curved", "curved", (1.25, 1.25, 1.25), 0., (.25, .25, .25)),
    ("half_phase_axis", "axis", (1., 1., 1.), 0., (.5, .5, .5)),
    ("quarter_phase_diagonal", "diagonal", (1., 1., 1.), 0., (.25, .25, .25)),
]


def spatial_fixture(configuration, focal=False):
    name, kind, spacing, angle, phase = configuration
    spacing = np.asarray(spacing)
    shape = (81, 81, 81)
    cosine, sine = np.cos(angle), np.sin(angle)
    i, j, k = np.indices(shape, dtype=float)
    # World coordinates calculated explicitly, not via production transforms.
    x, y, z = (i - 40) * spacing[0], (j - 40) * spacing[1], (k - 40) * spacing[2]
    world = np.stack((cosine * x + sine * z + phase[0], y + phase[1], -sine * x + cosine * z + phase[2]), axis=-1)
    center = np.array([2.1, -3.2, 0.])
    direction = np.array([.45, .25, 1.]) if kind == "diagonal" else np.array([0., 0., 1.])
    direction /= np.linalg.norm(direction)

    def truth(points):
        p = np.asarray(points) - center
        if kind == "curved":
            # Exact closest point on a finite circular arc, radius 60 mm.
            theta = np.clip(np.arctan2(p[..., 2], 60. - p[..., 0]), -.4, .4)
            nearest = np.stack((60. * (1 - np.cos(theta)), np.zeros_like(theta), 60. * np.sin(theta)), axis=-1)
            arc = theta * 60.
        else:
            arc = np.clip(np.sum(p * direction, axis=-1), -24., 24.)
            nearest = arc[..., None] * direction
        distance = np.linalg.norm(p - nearest, axis=-1)
        radius = np.where(np.abs(arc) <= 2., 2.2, 4.) if focal else np.full_like(arc, 4.)
        return arc, distance, radius

    arc, distance, radius = truth(world)
    mask = (distance <= radius).astype(np.uint8)
    rotation = np.array([[cosine, 0., sine], [0., 1., 0.], [-sine, 0., cosine]])
    affine = np.eye(4); affine[:3, :3] = rotation @ np.diag(spacing)
    affine[:3, 3] = np.asarray(phase) - affine[:3, :3] @ np.array([40., 40., 40.])
    geometry = VolumeGeometry(shape=shape, affine=affine.tolist(), array_axis_order="nifti_i_j_k", world_convention="RAS", world_unit="mm")
    source = bound_source(mask, geometry)

    def independently_world(ijk):
        p = np.asarray(ijk, dtype=float)
        x, y, z = ((p[:, axis] - 40.) * spacing[axis] for axis in range(3))
        return np.column_stack((cosine * x + sine * z + phase[0], y + phase[1], -sine * x + cosine * z + phase[2]))

    return mask, geometry, spacing, source, truth, independently_world


def bound_source(mask, geometry):
    # Caller-supplied SYNTHETIC identifier, not a real CT hash or app record.
    return {"source_sha256": "a" * 64, "mask_sha256": mask_identity(mask, 1),
            "geometry_fingerprint": geometry_fingerprint(geometry, "a" * 64),
            "mask_role": "supplied_segmentation", "parent_segmentation_result_id": None, "target_label": 1}


def y_fixture(radius=3.):
    i, j, k = np.indices((73, 73, 73), dtype=float)
    grid = np.stack((i, j, k), axis=-1)
    segments = [([36, 36, 8], [36, 36, 36]), ([36, 36, 36], [18, 36, 60]), ([36, 36, 36], [54, 36, 60])]
    distance = np.full(grid.shape[:-1], np.inf)
    for start, end in segments:
        start, end = np.array(start), np.array(end)
        direction = end - start
        t = np.clip(np.sum((grid - start) * direction, axis=-1) / np.dot(direction, direction), 0., 1.)
        distance = np.minimum(distance, np.linalg.norm(grid - start - t[..., None] * direction, axis=-1))
    mask = (distance <= radius).astype(np.uint8)
    g = VolumeGeometry(shape=mask.shape, affine=np.eye(4).tolist(), array_axis_order="nifti_i_j_k", world_convention="RAS", world_unit="mm")
    return mask, g, (1., 1., 1.), bound_source(mask, g)
