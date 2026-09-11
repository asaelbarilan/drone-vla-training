"""Stage a byte-preserving Gemma vision projector for the Windows runtime bug.
Requires gguf; never edits the source model or registers/loads any model.
"""

import argparse
import hashlib
import json
from pathlib import Path

import gguf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-audio", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a projector")
    print("Reading source metadata", flush=True)
    source = gguf.GGUFReader(args.source)
    assert source.fields["general.architecture"].contents() == "gemma4"
    tensors = [
        t
        for t in source.tensors
        if t.name.startswith("v.")
        or t.name == "mm.input_projection.weight"
        or (args.include_audio and t.name.startswith(("a.", "mm.a.")))
    ]
    assert (
        next(t for t in tensors if t.name == "v.patch_embd.weight").tensor_type
        == gguf.GGMLQuantizationType.F16
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = gguf.GGUFWriter(args.output, "clip")
    for suffix in (
        "block_count",
        "embedding_length",
        "feed_forward_length",
        "attention.head_count",
        "attention.layer_norm_epsilon",
        "patch_size",
    ):
        field = source.fields["gemma4.vision." + suffix]
        writer.add_key_value("clip.vision." + suffix, field.contents(), field.types[0])
    writer.add_uint32("clip.vision.image_size", 224)
    writer.add_uint32(
        "clip.vision.projection_dim", source.fields["gemma4.embedding_length"].contents()
    )
    writer.add_bool("clip.has_vision_encoder", True)
    writer.add_bool("clip.has_audio_encoder", args.include_audio)
    writer.add_string("clip.vision.projector_type", "gemma4v")
    writer.add_array("clip.vision.image_mean", [0.0, 0.0, 0.0])
    writer.add_array("clip.vision.image_std", [1.0, 1.0, 1.0])

    def output_name(name):
        if not args.include_audio:
            return name
        top = {
            "a.pre_encode.out.weight": "a.input_projection.weight",
            "a.pre_encode.out.bias": "a.input_projection.bias",
            "mm.a.fc.weight": "a.pre_encode.out.weight",
            "mm.a.fc.bias": "a.pre_encode.out.bias",
        }
        if name in top:
            return top[name]
        if name.startswith("a.blk."):
            for old, new in (
                ("ln1", "attn_pre_norm"),
                ("ln2", "attn_post_norm"),
                ("layer_pre_norm", "ln2"),
                ("linear_pos", "attn_k_rel"),
            ):
                if name.endswith("." + old + ".weight"):
                    return name[: -len(old + ".weight")] + new + ".weight"
        return name

    if args.include_audio:
        for suffix in (
            "block_count",
            "embedding_length",
            "feed_forward_length",
            "attention.head_count",
            "attention.layer_norm_epsilon",
        ):
            field = source.fields["gemma4.audio." + suffix]
            writer.add_key_value("clip.audio." + suffix, field.contents(), field.types[0])
        writer.add_uint32("clip.audio.num_mel_bins", 128)
        writer.add_uint32(
            "clip.audio.projection_dim", source.fields["gemma4.embedding_length"].contents()
        )
        writer.add_string("clip.audio.projector_type", "gemma4a")
    records = {}
    for tensor in tensors:
        writer.add_tensor(output_name(tensor.name), tensor.data, raw_dtype=tensor.tensor_type)
        records[output_name(tensor.name)] = {
            "type": int(tensor.tensor_type),
            "shape": tensor.shape.tolist(),
            "sha256": hashlib.sha256(tensor.data.tobytes()).hexdigest(),
        }
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    result = gguf.GGUFReader(args.output)
    assert len(result.tensors) == len(tensors)
    for tensor in result.tensors:
        assert records[tensor.name] == {
            "type": int(tensor.tensor_type),
            "shape": tensor.shape.tolist(),
            "sha256": hashlib.sha256(tensor.data.tobytes()).hexdigest(),
        }
    report = {
        "source": str(args.source),
        "output": str(args.output),
        "source_unchanged": True,
        "includes_audio": args.include_audio,
        "tensor_count": len(tensors),
        "tensor_bytes": sum(t.n_bytes for t in tensors),
        "projector_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "verified_tensors": records,
    }
    args.output.with_suffix(".verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "verified_tensors"}), flush=True)


if __name__ == "__main__":
    main()
