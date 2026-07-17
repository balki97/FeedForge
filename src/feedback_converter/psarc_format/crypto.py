import zlib

from construct import Int32ul
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:
    from cryptography.hazmat.decrepit.ciphers.modes import CFB
except ImportError:  # pragma: no cover - older cryptography
    CFB = modes.CFB

ARC_KEY = bytes.fromhex(
    "C53DB23870A1A2F71CAE64061FDD0E1157309DC85204D4C5BFDF25090DF2572C"
)
ARC_IV = bytes.fromhex("E915AA018FEF71FC508132E4BB4CEB42")
ARC_CIPHER = Cipher(algorithms.AES(ARC_KEY), CFB(ARC_IV))

MAC_KEY = bytes.fromhex(
    "9821330E34B91F70D0A48CBD625993126970CEA09192C0E6CDA676CC9838289D"
)

WIN_KEY = bytes.fromhex(
    "CB648DF3D12A16BF71701414E69619EC171CCA5D2A142E3E59DE7ADDA18A3A30"
)

PRF_KEY = bytes.fromhex(
    "728B369E24ED0134768511021812AFC0A3C25D02065F166B4BCC58CD2644F29E"
)

CONFIG_KEY = bytes.fromhex(
    "378B9026EE7DE70B8AF124C1E30978670F9EC8FD5E7285A86442DD73068C0473"
)


def decrypt_bom(data):
    decryptor = ARC_CIPHER.decryptor()
    return decryptor.update(data) + decryptor.finalize()


def encrypt_bom(data):
    encryptor = ARC_CIPHER.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def aes_sng(key, iv):
    return Cipher(algorithms.AES(key), modes.CTR(iv))


def decrypt_sng(data, key):
    if len(data) < 24:
        return data
    iv, data = data[8:24], data[24:]
    decryptor = aes_sng(key, iv).decryptor()
    decrypted = decryptor.update(data) + decryptor.finalize()
    length, payload = Int32ul.parse(decrypted[:4]), decrypted[4:]
    payload = zlib.decompress(payload)
    assert len(payload) == length
    return payload


def encrypt_sng(data, key):
    header = Int32ul.build(74) + Int32ul.build(3)
    iv = bytes(16)
    payload = Int32ul.build(len(data))
    payload += zlib.compress(data, zlib.Z_BEST_COMPRESSION)
    encryptor = aes_sng(key, iv).encryptor()
    encrypted = encryptor.update(payload) + encryptor.finalize()
    return header + iv + encrypted + bytes(56)


def decrypt_psarc(content):
    # TODO: profile, config
    content = content.copy()
    for k in content:
        normalized = k.replace("\\", "/").lower()
        if "songs/bin/macos/" in normalized:
            content[k] = decrypt_sng(content[k], MAC_KEY)
        elif "songs/bin/generic/" in normalized:
            content[k] = decrypt_sng(content[k], WIN_KEY)
    return content


def encrypt_psarc(content):
    # TODO: profile, config
    content = content.copy()
    for k in content:
        normalized = k.replace("\\", "/").lower()
        if "songs/bin/macos/" in normalized:
            content[k] = encrypt_sng(content[k], MAC_KEY)
        elif "songs/bin/generic/" in normalized:
            content[k] = encrypt_sng(content[k], WIN_KEY)
    return content
