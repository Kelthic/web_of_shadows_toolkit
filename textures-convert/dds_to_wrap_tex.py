import os
import sys
import struct
import argparse
from pathlib import Path


def get_filename_hash(name: str) -> int:
    result = 0
    for ch in name.lower():
        result = (result * 33 + ord(ch)) & 0xFFFFFFFF
    return result


_DDS_FORMATS = {
    b'DXT1': (0x04, 0,  [0, 0, 0, 0]),
    b'DXT3': (0x04, 0,  [0, 0, 0, 0]),
    b'DXT5': (0x04, 0,  [0, 0, 0, 0]),
    0x15:    (0x41, 32, [0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000]),  # ARGB32
    0x16:    (0x40, 32, [0x00FF0000, 0x0000FF00, 0x000000FF, 0x00000000]),  # XRGB32
    0x32:    (0x20000, 8, [0x000000FF, 0, 0, 0]),                           # A8
}

# DDS pixel format flags
_DDPF_ALPHAPIXELS = 0x00000001
_DDPF_ALPHA       = 0x00000002
_DDPF_FOURCC      = 0x00000004
_DDPF_RGB         = 0x00000040
_DDPF_LUMINANCE   = 0x00020000


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _pad_to(data: bytes, alignment: int, pad_byte: bytes = b'\xA1') -> bytes:
    rem = len(data) % alignment
    if rem:
        data += pad_byte * (alignment - rem)
    return data

def build_texture_header(width: int, height: int, mips: int,
                         fourcc_or_id, filename_hash: int) -> bytes:

    hdr = bytearray(64)
    struct.pack_into('<I', hdr, 0x0C, filename_hash)
    struct.pack_into('<I', hdr, 0x18, width)
    struct.pack_into('<I', hdr, 0x1C, height)
    struct.pack_into('<I', hdr, 0x24, max(1, mips))

    if isinstance(fourcc_or_id, bytes):
        hdr[0x28:0x2C] = fourcc_or_id[:4]
    else:
        struct.pack_into('<I', hdr, 0x28, fourcc_or_id)

    return bytes(hdr)


def parse_texture_header(data: bytes):

    if len(data) < 64:
        raise ValueError(f"Textures header too short: {len(data)} byte")
    filename_hash = struct.unpack_from('<I', data, 0x0C)[0]
    width         = struct.unpack_from('<I', data, 0x18)[0]
    height        = struct.unpack_from('<I', data, 0x1C)[0]
    mips          = struct.unpack_from('<I', data, 0x24)[0]
    fourcc        = data[0x28:0x2C]
    return filename_hash, width, height, mips, fourcc


def build_wrap_file(component0: bytes, component1: bytes,
                    archive_hash: int = 0) -> bytes:

    # Offset  Size   Field
    # 0x00    4      magic "WRAP"
    # 0x04    4      archiveFilenameHash
    # 0x08    4      pPatchTable (relative)
    # 0x0C    4      componentCount = 2
    # 0x10    4      pComponentTable (relative)
    # [componentTable: 2 × {u32 size, i32 pComponent (relative)}]
    # [padding to 16]
    # [patchTable:
    #    u32 externalPatchCount = 0
    #    i32 pExternalPatches   (relative)
    #    u32 internalPatchCount = 0
    #    i32 pInternalPatches   (relative)
    #    u32 globalPatchCount   = 0
    #    i32 pGlobalPatches     (relative)
    #    padding to 16
    #    <externalPatches>
    #    padding to 16
    #    <internalPatches>
    #    padding to 16
    #    <globalPatches>
    # ]
    # [padding to 16]
    # [component0]
    # b'PHYS'
    # [component1]

    c0 = component0
    c1 = component1

    off_wrapper_hdr = 0
    sz_wrapper_hdr  = 20  # "WRAP" + archiveHash + pPatchTable + componentCount + pComponentTable

    off_comp_table = off_wrapper_hdr + sz_wrapper_hdr
    sz_comp_table  = 8 * 2  

    off_after_comp_table = off_comp_table + sz_comp_table  # 36
    off_patch_table = _align(off_after_comp_table, 16)     # 48

    sz_patch_hdr = 24
    off_after_patch_hdr = off_patch_table + sz_patch_hdr   # 72

    off_ext_patches = _align(off_after_patch_hdr, 16)      # 80
    off_int_patches = _align(off_ext_patches, 16)          # 80  
    off_gbl_patches = _align(off_int_patches, 16)          # 80  
    off_after_patch = _align(off_gbl_patches, 16)          # 80

    off_file_section = _align(off_after_patch, 16)         # 80

    off_c0 = off_file_section
    sz_c0  = len(c0)

    off_phys = off_c0 + sz_c0
    sz_phys  = 4

    off_c1 = off_phys + sz_phys
    sz_c1  = len(c1)

    total = off_c1 + sz_c1

    buf = bytearray(total)

    buf[0:4] = b'WRAP'
    struct.pack_into('<I', buf, 4,  archive_hash)
    # pPatchTable (relative от offset 8)
    struct.pack_into('<i', buf, 8,  off_patch_table - 8)
    # componentCount
    struct.pack_into('<I', buf, 12, 2)
    # pComponentTable (relative от offset 16)
    struct.pack_into('<i', buf, 16, off_comp_table - 16)

    # componentTable[0]: size=len(c0), ptr relative к offset of ptr field
    struct.pack_into('<I', buf, off_comp_table + 0, sz_c0)
    ptr0_off = off_comp_table + 4
    struct.pack_into('<i', buf, ptr0_off, off_c0 - ptr0_off)

    # componentTable[1]: size=len(c1), ptr relative к offset of ptr field
    struct.pack_into('<I', buf, off_comp_table + 8, sz_c1)
    ptr1_off = off_comp_table + 12
    struct.pack_into('<i', buf, ptr1_off, off_c1 - ptr1_off)

    # patchTable header
    # externalPatchCount=0, pExternalPatches (relative)
    struct.pack_into('<I', buf, off_patch_table + 0,  0)
    pep_off = off_patch_table + 4
    struct.pack_into('<i', buf, pep_off, off_ext_patches - pep_off)
    # internalPatchCount=0, pInternalPatches (relative)
    struct.pack_into('<I', buf, off_patch_table + 8,  0)
    pip_off = off_patch_table + 12
    struct.pack_into('<i', buf, pip_off, off_int_patches - pip_off)
    # globalPatchCount=0, pGlobalPatches (relative)
    struct.pack_into('<I', buf, off_patch_table + 16, 0)
    pgp_off = off_patch_table + 20
    struct.pack_into('<i', buf, pgp_off, off_gbl_patches - pgp_off)

    for i in range(off_after_comp_table, off_patch_table):
        buf[i] = 0xA1
    for i in range(off_after_patch, off_file_section):
        buf[i] = 0xA1

    # component0
    buf[off_c0:off_c0 + sz_c0] = c0

    buf[off_phys:off_phys + 4] = b'PHYS'

    # component1
    buf[off_c1:off_c1 + sz_c1] = c1

    return bytes(buf)


def parse_wrap_file(data: bytes):

    if data[:4] != b'WRAP':
        raise ValueError("The file doesn't start with 'WRAP'")

    # archive_hash = struct.unpack_from('<I', data, 4)[0]
    p_patch_table_rel = struct.unpack_from('<i', data, 8)[0]
    # component_count  = struct.unpack_from('<I', data, 12)[0]
    p_comp_table_rel  = struct.unpack_from('<i', data, 16)[0]

    off_comp_table = 16 + p_comp_table_rel

    sz_c0   = struct.unpack_from('<I', data, off_comp_table + 0)[0]
    ptr0_rel = struct.unpack_from('<i', data, off_comp_table + 4)[0]
    off_c0  = (off_comp_table + 4) + ptr0_rel

    sz_c1   = struct.unpack_from('<I', data, off_comp_table + 8)[0]
    ptr1_rel = struct.unpack_from('<i', data, off_comp_table + 12)[0]
    off_c1  = (off_comp_table + 12) + ptr1_rel

    c0 = data[off_c0: off_c0 + sz_c0]
    c1 = data[off_c1: off_c1 + sz_c1]
    return c0, c1


def read_dds(path: Path):

    data = path.read_bytes()
    if data[:4] != b'DDS ':
        raise ValueError(f"Not DDS file: {path}")

    hdr = data[4:128]
    height, width = struct.unpack_from('<II', hdr, 8)
    mips = struct.unpack_from('<I', hdr, 24)[0]
    pf_flags = struct.unpack_from('<I', hdr, 76)[0]
    pf_fourcc = hdr[80:84]  

    pixel_data = data[128:]

    if pf_flags & _DDPF_FOURCC:
        effective = pf_fourcc
    else:
        if (pf_flags & _DDPF_RGB) and (pf_flags & _DDPF_ALPHAPIXELS):
            effective = 0x15  
        elif pf_flags & _DDPF_RGB:
            effective = 0x16  
        elif pf_flags & _DDPF_LUMINANCE:
            effective = 0x32  
        elif pf_flags & _DDPF_ALPHA:
            effective = 0x32  
        else:
            effective = pf_fourcc

    return width, height, mips, effective, pixel_data


def build_dds(width: int, height: int, mips: int,
              fourcc: bytes, pixel_data: bytes) -> bytes:
                  
    fmt_key = fourcc
    if fmt_key not in _DDS_FORMATS:
        fmt_int = struct.unpack_from('<I', fourcc)[0]
        fmt_key = fmt_int

    fmt = _DDS_FORMATS.get(fmt_key)
    if fmt is None:
        raise ValueError(f"Unknown texture format: {fourcc.hex()} / {struct.unpack('<I', fourcc)[0]:#010x}")

    ngl_code, bpp, masks = fmt
    is_compressed = (ngl_code == 0x04)

    flags = 0x21007
    if mips > 1:
        flags |= 0x00020000

    if is_compressed:
        block_size = 8 if fmt_key == b'DXT1' else 16
        linear_size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
    else:
        linear_size = width * (bpp // 8)

    out = bytearray()
    out += b'DDS '
    out += struct.pack('<I', 124)            
    out += struct.pack('<I', flags)          
    out += struct.pack('<I', height)         
    out += struct.pack('<I', width)          
    out += struct.pack('<I', linear_size)    
    out += struct.pack('<I', 0)              
    out += struct.pack('<I', max(1, mips))   
    out += b'\x00' * 44                     

    out += struct.pack('<I', 32)             
    if is_compressed:
        out += struct.pack('<I', _DDPF_FOURCC)       
        out += fourcc                                
        out += struct.pack('<IIIII', 0, 0, 0, 0, 0)  
    else:
        pf_flags = 0
        if ngl_code == 0x41:
            pf_flags = _DDPF_RGB | _DDPF_ALPHAPIXELS
        elif ngl_code == 0x40:
            pf_flags = _DDPF_RGB
        elif ngl_code == 0x20000:
            pf_flags = _DDPF_LUMINANCE
        out += struct.pack('<I', pf_flags)           
        out += b'\x00\x00\x00\x00'                  
        out += struct.pack('<IIIII', bpp, *masks)    

    caps1 = 0x401008  
    out += struct.pack('<I', caps1)
    out += b'\x00' * 16  

    # Pixel data
    out += pixel_data

    return bytes(out)


def dds_to_warp_tex(dds_path: Path, output_path: Path = None, verbose: bool = True):
    width, height, mips, effective, pixel_data = read_dds(dds_path)

    stem = dds_path.stem
    fname_hash = get_filename_hash(stem)

    comp0 = build_texture_header(width, height, mips, effective, fname_hash)
    comp1 = pixel_data

    wrap_data = build_wrap_file(comp0, comp1)

    if output_path is None:
        output_path = dds_path.with_suffix('').with_suffix('.warp.tex')
        output_path = dds_path.parent / (stem + '.warp.tex')

    output_path.write_bytes(wrap_data)
    if verbose:
        fmt_str = effective.decode() if isinstance(effective, bytes) else f'0x{effective:X}'
        print(f"[OK] {dds_path.name}  ->  {output_path.name}")
        print(f"     {width}x{height}, mips={mips}, format={fmt_str}, hash=0x{fname_hash:08X}")
    return output_path


def warp_tex_to_dds(tex_path: Path, output_path: Path = None, verbose: bool = True):

    raw = tex_path.read_bytes()

    comp0, comp1 = parse_wrap_file(raw)
    fname_hash, width, height, mips, fourcc = parse_texture_header(comp0)

    dds_data = build_dds(width, height, mips, fourcc, comp1)

    if output_path is None:
        # убираем .warp.tex -> .dds
        name = tex_path.name
        if name.lower().endswith('.warp.tex'):
            name = name[:-len('.warp.tex')]
        elif name.lower().endswith('.tex'):
            name = name[:-4]
        output_path = tex_path.parent / (name + '.dds')

    output_path.write_bytes(dds_data)
    if verbose:
        fmt_str = fourcc.decode('latin-1') if all(32 <= b < 127 for b in fourcc) else fourcc.hex()
        print(f"[OK] {tex_path.name}  ->  {output_path.name}")
        print(f"     {width}x{height}, mips={mips}, format={fmt_str}, hash=0x{fname_hash:08X}")
    return output_path


def old_tex_to_warp_tex(tex0_path: Path, output_path: Path = None, verbose: bool = True):

    tex1_path = Path(str(tex0_path).replace('.0.tex', '.1.tex'))
    if not tex1_path.exists():
        raise FileNotFoundError(f"Data file not found: {tex1_path}")

    comp0 = tex0_path.read_bytes()
    comp1 = tex1_path.read_bytes()

    if len(comp0) < 64:
        raise ValueError(f"component0 too small: {len(comp0)} byte")

    wrap_data = build_wrap_file(comp0, comp1)

    if output_path is None:
        stem = tex0_path.name.replace('.0.tex', '')
        output_path = tex0_path.parent / (stem + '.warp.tex')

    output_path.write_bytes(wrap_data)
    if verbose:
        fname_hash, width, height, mips, fourcc = parse_texture_header(comp0)
        print(f"[OK] {tex0_path.name} + {tex1_path.name}  ->  {output_path.name}")
        print(f"     {width}x{height}, mips={mips}, hash=0x{fname_hash:08X}")
    return output_path


def process_path(p: Path, output_dir: Path, force: bool, verbose: bool) -> bool:
    name_lower = p.name.lower()

    try:
        if name_lower.endswith('.dds'):
            stem = p.stem
            out = (output_dir / (stem + '.warp.tex')) if output_dir else None
            if out and out.exists() and not force:
                print(f"[SKIP] already exists: {out}")
                return True
            dds_to_warp_tex(p, out, verbose)

        elif name_lower.endswith('.warp.tex'):
            stem = p.name[:-len('.warp.tex')]
            out = (output_dir / (stem + '.dds')) if output_dir else None
            if out and out.exists() and not force:
                print(f"[SKIP] already exists: {out}")
                return True
            warp_tex_to_dds(p, out, verbose)

        elif name_lower.endswith('.0.tex'):
            stem = p.name.replace('.0.tex', '')
            out = (output_dir / (stem + '.warp.tex')) if output_dir else None
            if out and out.exists() and not force:
                print(f"[SKIP] already exists: {out}")
                return True
            old_tex_to_warp_tex(p, out, verbose)

        else:
            return False

    except Exception as e:
        print(f"[ERR] {p.name}: {e}", file=sys.stderr)
        return False

    return True


def main():
    parser = argparse.ArgumentParser(
        prog='dds_to_warp_tex',
        description='DDS converter <-> *.warp.tex for Spider-Man: Web of Shadows (PC)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s texture.dds                  # DDS to texture.warp.tex\n"
            "  %(prog)s texture.warp.tex             # warp.tex to texture.dds\n"
            "  %(prog)s *.dds -o ./output/           # batch conversion to a folder\n"
            "  %(prog)s textures/                    # each DDS/warp.tex in directory\n"
            "  %(prog)s texture.0.tex                # old .0/.1.tex to .warp.tex\n"
        ),
    )

    parser.add_argument('inputs', nargs='+', metavar='FILE_OR_DIR',
                        help='DDS, .warp.tex, .0.tex file(-s) or directory')
    parser.add_argument('-o', '--output', metavar='DIR',
                        help='Output directory (by default - next to the input directory)')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Overwrite existing files')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Do not display progress')

    args = parser.parse_args()
    verbose = not args.quiet

    output_dir = Path(args.output) if args.output else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    for inp in args.inputs:
        p = Path(inp)

        if p.is_dir():
            files = sorted(p.iterdir())
            for f in files:
                if f.is_file() and (
                    f.name.lower().endswith('.dds') or
                    f.name.lower().endswith('.warp.tex') or
                    f.name.lower().endswith('.0.tex')
                ):
                    if process_path(f, output_dir, args.force, verbose):
                        processed += 1
        elif p.is_file():
            if process_path(p, output_dir, args.force, verbose):
                processed += 1
        else:
            # Может быть глобальный паттерн, уже раскрытый шеллом
            print(f"[WARN] Not found: {p}", file=sys.stderr)

    if verbose:
        print(f"\nFiles processed: {processed}")


if __name__ == '__main__':
    main()
