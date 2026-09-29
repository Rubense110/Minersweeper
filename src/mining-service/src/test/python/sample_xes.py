#!/usr/bin/env python3
"""Make a deterministic, bounded-memory trace sample of an XES log.

The source is opened for reading only; the output path must not already exist.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import xml.etree.ElementTree as ET
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sample(source_path: Path, output_path: Path, count: int, seed: int) -> dict:
    if source_path.resolve() == output_path.resolve():
        raise ValueError("sample output must differ from the source log")
    if output_path.exists():
        raise FileExistsError(f"sample already exists: {output_path}")
    if count < 1:
        raise ValueError("sample size must be positive")

    source_before = digest(source_path)
    rng = random.Random(seed)
    stream = ET.iterparse(source_path, events=("start", "end"))
    first_event, root = next(stream)
    if first_event != "start" or local_name(root.tag) != "log":
        raise ValueError("source is not an XES log")
    log_attributes = dict(root.attrib)
    metadata = []
    selected = []
    trace_count = 0

    for event, element in stream:
        if event != "end" or element is root:
            continue
        name = local_name(element.tag)
        if name == "trace":
            trace_count += 1
            if len(selected) < count:
                selected.append((trace_count, copy.deepcopy(element)))
            else:
                position = rng.randrange(trace_count)
                if position < count:
                    selected[position] = (trace_count, copy.deepcopy(element))
            root.remove(element)
        elif element in root:
            metadata.append(copy.deepcopy(element))
            root.remove(element)

    if trace_count < count:
        raise ValueError(f"log has only {trace_count} traces, fewer than requested {count}")
    sampled_log = ET.Element(root.tag, log_attributes)
    sampled_log.extend(metadata)
    sampled_log.extend(trace for _, trace in sorted(selected))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as output:
        ET.ElementTree(sampled_log).write(output, encoding="utf-8", xml_declaration=True)
    source_after = digest(source_path)
    if source_before != source_after:
        raise RuntimeError("source log changed during sampling")

    return {
        "source": str(source_path),
        "source_sha256_before": source_before,
        "source_sha256_after": source_after,
        "source_traces": trace_count,
        "sample": str(output_path),
        "sample_sha256": digest(output_path),
        "sample_traces": len(selected),
        "sample_bytes": output_path.stat().st_size,
        "seed": seed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("sample", type=Path)
    parser.add_argument("--traces", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20260929)
    args = parser.parse_args()
    print(json.dumps(sample(args.source, args.sample, args.traces, args.seed), indent=2))
