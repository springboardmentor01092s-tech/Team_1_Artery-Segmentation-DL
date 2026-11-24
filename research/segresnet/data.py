"""Memory-mapped directory/ZIP_STORED cache access, without extracting CTs."""
from pathlib import Path
import hashlib
import json
import struct
import zipfile
import numpy as np


class CacheStore:
    def __init__(self, root):
        self.root = Path(root)
        self.archive = zipfile.ZipFile(root) if self.root.is_file() else None
        self.manifest = self.json("manifest.json")
        if self.manifest.get("schema_version") != "imagecas-cache/1.0":
            raise ValueError("Unsupported cache")
        if self.manifest.get("spacing_mm") != [1, 1, 1]:
            raise ValueError("This experiment requires the accepted 1 mm grid")
        training = self.manifest["training_ids"]
        validation = self.manifest["validation_ids"]
        if len(set(training + validation)) != len(training + validation):
            raise ValueError("Overlapping or duplicate split membership")
        if any(not str(x).isdigit() for x in training + validation):
            raise ValueError("Invalid canonical case IDs")

    def json(self, relative):
        data = self.archive.read(relative) if self.archive else (self.root / relative).read_bytes()
        return json.loads(data)

    def verify(self):
        """Stream every selected cache payload; identity is ZIP/directory invariant."""
        identities = {}

        def checked(relative, expected=None, expected_size=None):
            opener = self.archive.open(relative) if self.archive else (self.root / relative).open("rb")
            digest, size = hashlib.sha256(), 0
            with opener as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            value = digest.hexdigest()
            if expected is not None and (value != expected or size != expected_size):
                raise ValueError("Cache payload hash or size differs from saved provenance")
            identities[relative] = value

        checked("manifest.json")
        for split, key in (("Training", "training_ids"), ("Val", "validation_ids")):
            for case_id in self.manifest[key]:
                record = self.info(split, case_id)
                checked(f"{split}/{case_id}/case.json")
                required = {"image.npy", "mask.npy"} | ({"reference-native.nii.gz"} if split == "Val" else set())
                if {r["name"] for r in record["files"]} != required or len(record["files"]) != len(required):
                    raise ValueError("Unexpected cache payload inventory")
                for row in record["files"]:
                    checked(f'{split}/{case_id}/{row["name"]}', row["sha256"], row["bytes"])
        canonical = json.dumps(identities, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def info(self, split, case_id):
        self.check_member(split, case_id)
        record = self.json(f"{split}/{case_id}/case.json")
        if record["case_id"] != case_id or record["split"] != split:
            raise ValueError("Cache case identity differs")
        return record

    def check_member(self, split, case_id):
        key = {"Training": "training_ids", "Val": "validation_ids"}.get(split)
        if key is None or case_id not in self.manifest[key]:
            raise ValueError("Case is not in the permitted Training/Val split")

    def array(self, split, case_id, kind):
        self.check_member(split, case_id)
        if kind not in ("image", "mask"):
            raise ValueError("Unsupported cache array")
        relative = f"{split}/{case_id}/{kind}.npy"
        if self.archive is None:
            value = np.load(self.root / relative, mmap_mode="r", allow_pickle=False)
            if value.ndim != 3 or value.dtype != np.dtype("float16" if kind == "image" else "uint8"):
                raise ValueError("Unexpected cache dtype or dimensions")
            return value
        entry = self.archive.getinfo(relative)
        if entry.compress_type != zipfile.ZIP_STORED:
            raise ValueError("Memory mapping requires an uncompressed ZIP_STORED member")
        with self.root.open("rb") as stream:
            stream.seek(entry.header_offset)
            header = stream.read(30)
            if header[:4] != b"PK\x03\x04":
                raise ValueError("Invalid ZIP local header")
            name_size, extra_size = struct.unpack_from("<HH", header, 26)
            start = entry.header_offset + 30 + name_size + extra_size
            stream.seek(start)
            version = np.lib.format.read_magic(stream)
            if version == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
            elif version == (2, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
            else:
                raise ValueError("Unsupported NPY header")
            offset = stream.tell()
        if dtype.hasobject or len(shape) != 3 or dtype != np.dtype("float16" if kind == "image" else "uint8"):
            raise ValueError("Unexpected cache dtype or dimensions")
        return np.memmap(self.root, dtype=dtype, mode="r", offset=offset, shape=shape,
                         order="F" if fortran else "C")

    def native_reference(self, case_id, output):
        self.check_member("Val", case_id)
        relative = f"Val/{case_id}/reference-native.nii.gz"
        if not self.archive:
            return self.root / relative
        destination = Path(output) / "native-references" / f"{case_id}.nii.gz"
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(self.archive.read(relative))
        return destination


def crop_patch(array, center, size):
    shape = np.asarray(array.shape)
    start = np.asarray(center, dtype=int) - size // 2
    end = start + size
    lo, hi = np.maximum(start, 0), np.minimum(end, shape)
    slices = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    patch = np.asarray(array[slices])
    padding = tuple((int(a), int(b)) for a, b in zip(lo - start, end - hi))
    return np.pad(patch, padding, mode="constant")


def patch_batch(store, step, batch_size=2, size=96, seed=20261117, augment=True):
    images, labels = [], []
    ids = store.manifest["training_ids"]
    rng = np.random.default_rng(seed + step)
    for _ in range(batch_size):
        case_id = ids[int(rng.integers(len(ids)))]
        image, mask = (store.array("Training", case_id, k) for k in ("image", "mask"))
        if image.shape != mask.shape:
            raise ValueError("Cache image/mask mismatch")
        if rng.random() < 2 / 3:
            foreground = np.argwhere(mask > 0)
            if len(foreground) == 0:
                raise ValueError("No foreground sampling support")
            center = foreground[int(rng.integers(len(foreground)))]
        else:
            center = [rng.integers(n) for n in image.shape]
        x, y = crop_patch(image, center, size), crop_patch(mask, center, size)
        if augment:
            for axis in range(3):
                if rng.random() < .5:
                    x, y = np.flip(x, axis), np.flip(y, axis)
            turns = int(rng.integers(4))
            x, y = np.rot90(x, turns, (0, 1)), np.rot90(y, turns, (0, 1))
        images.append(np.array(x[None], dtype=np.float32, copy=True, order="C"))
        labels.append(np.array(y[None], dtype=np.int64, copy=True, order="C"))
    return np.stack(images), np.stack(labels)
