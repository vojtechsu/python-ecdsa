from __future__ import division

from . import der, ecdsa, ellipticcurve
from .util import orderlen, number_to_string, string_to_number
from ._compat import normalise_bytes


# orderlen was defined in this module previously, so keep it in __all__,
# will need to mark it as deprecated later
__all__ = [
    "UnknownCurveError",
    "orderlen",
    "Curve",
    "SECP112r1",
    "SECP112r2",
    "SECP128r1",
    "SECP160r1",
    "NIST192p",
    "NIST224p",
    "NIST256p",
    "NIST384p",
    "NIST521p",
    "curves",
    "find_curve",
    "SECP256k1",
    "BRAINPOOLP160r1",
    "BRAINPOOLP192r1",
    "BRAINPOOLP224r1",
    "BRAINPOOLP256r1",
    "BRAINPOOLP320r1",
    "BRAINPOOLP384r1",
    "BRAINPOOLP512r1",
    "PRIME_FIELD_OID",
    "CHARACTERISTIC_TWO_FIELD_OID",
]


PRIME_FIELD_OID = (1, 2, 840, 10045, 1, 1)
CHARACTERISTIC_TWO_FIELD_OID = (1, 2, 840, 10045, 1, 2)


class UnknownCurveError(Exception):
    pass


class Curve:
    def __init__(self, name, curve, generator, oid, openssl_name=None):
        self.name = name
        self.openssl_name = openssl_name  # maybe None
        self.curve = curve
        self.generator = generator
        self.order = generator.order()
        self.baselen = orderlen(self.order)
        self.verifying_key_length = 2 * orderlen(curve.p())
        self.signature_length = 2 * self.baselen
        self.oid = oid
        if oid:
            self.encoded_oid = der.encode_oid(*oid)

    def __eq__(self, other):
        if isinstance(other, Curve):
            return (
                self.curve == other.curve and self.generator == other.generator
            )
        return NotImplemented

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return self.name

    def to_der(self, encoding=None, point_encoding="uncompressed"):
        """Serialise the curve parameters to binary string.

        :param str encoding: the format to save the curve parameters in.
            Default is ``named_curve``, with fallback being the ``explicit``
            if the OID is not set for the curve.
        :param str point_encoding: the point encoding of the generator when
            explicit curve encoding is used. Ignored for ``named_curve``
            format.
        """
        if encoding is None:
            if self.oid:
                encoding = "named_curve"
            else:
                encoding = "explicit"

        if encoding == "named_curve":
            if not self.oid:
                raise UnknownCurveError(
                    "Can't encode curve using named_curve encoding without "
                    "associated curve OID"
                )
            return der.encode_oid(*self.oid)

        # encode the ECParameters sequence
        curve_p = self.curve.p()
        version = der.encode_integer(1)
        field_id = der.encode_sequence(
            der.encode_oid(*PRIME_FIELD_OID), der.encode_integer(curve_p)
        )
        curve = der.encode_sequence(
            der.encode_octet_string(
                number_to_string(self.curve.a() % curve_p, curve_p)
            ),
            der.encode_octet_string(
                number_to_string(self.curve.b() % curve_p, curve_p)
            ),
        )
        base = der.encode_octet_string(self.generator.to_bytes(point_encoding))
        order = der.encode_integer(self.generator.order())
        seq_elements = [version, field_id, curve, base, order]
        if self.curve.cofactor():
            cofactor = der.encode_integer(self.curve.cofactor())
            seq_elements.append(cofactor)

        return der.encode_sequence(*seq_elements)

    @staticmethod
    def from_der(data):
        """Decode the curve parameters from DER file.

        :param data: the binary string to decode the parameters from
        :type data: bytes-like object
        """
        data = normalise_bytes(data)
        if not der.is_sequence(data):
            oid, empty = der.remove_object(data)
            if empty:
                raise der.UnexpectedDER("Unexpected data after OID")
            return find_curve(oid)

        seq, empty = der.remove_sequence(data)
        if empty:
            raise der.UnexpectedDER(
                "Unexpected data after ECParameters structure"
            )
        # decode the ECParameters sequence
        version, rest = der.remove_integer(seq)
        if version != 1:
            raise der.UnexpectedDER("Unknown parameter encoding format")
        field_id, rest = der.remove_sequence(rest)
        curve, rest = der.remove_sequence(rest)
        base_bytes, rest = der.remove_octet_string(rest)
        order, rest = der.remove_integer(rest)
        cofactor = None
        if rest:
            cofactor, rest = der.remove_integer(rest)

        # decode the ECParameters.fieldID sequence
        field_type, rest = der.remove_object(field_id)
        if field_type == CHARACTERISTIC_TWO_FIELD_OID:
            raise UnknownCurveError("Characteristic 2 curves unsupported")
        if field_type != PRIME_FIELD_OID:
            raise UnknownCurveError(
                "Unknown field type: {0}".format(field_type)
            )
        prime, empty = der.remove_integer(rest)
        if empty:
            raise der.UnexpectedDER(
                "Unexpected data after ECParameters.fieldID.Prime-p element"
            )

        # decode the ECParameters.curve sequence
        curve_a_bytes, rest = der.remove_octet_string(curve)
        curve_b_bytes, rest = der.remove_octet_string(rest)
        # seed can be defined here, but we don't parse it, so ignore `rest`

        curve_a = string_to_number(curve_a_bytes)
        curve_b = string_to_number(curve_b_bytes)

        curve_fp = ellipticcurve.CurveFp(prime, curve_a, curve_b, cofactor)

        # decode the ECParameters.base point

        base = ellipticcurve.PointJacobi.from_bytes(
            curve_fp,
            base_bytes,
            valid_encodings=("uncompressed", "compressed", "hybrid"),
            order=order,
            generator=True,
        )
        tmp_curve = Curve("unknown", curve_fp, base, None)

        # if the curve matches one of the well-known ones, use the well-known
        # one in preference, as it will have the OID and name associated
        for i in curves:
            if tmp_curve == i:
                return i
        return tmp_curve


# the SEC curves
SECP112r1 = Curve(
    "SECP112r1",
    ecdsa.curve_112r1,
    ecdsa.generator_112r1,
    (1, 3, 132, 0, 6),
    "secp112r1",
)


SECP112r2 = Curve(
    "SECP112r2",
    ecdsa.curve_112r2,
    ecdsa.generator_112r2,
    (1, 3, 132, 0, 7),
    "secp112r2",
)


SECP128r1 = Curve(
    "SECP128r1",
    ecdsa.curve_128r1,
    ecdsa.generator_128r1,
    (1, 3, 132, 0, 28),
    "secp128r1",
)


SECP160r1 = Curve(
    "SECP160r1",
    ecdsa.curve_160r1,
    ecdsa.generator_160r1,
    (1, 3, 132, 0, 8),
    "secp160r1",
)


# the NIST curves
NIST192p = Curve(
    "NIST192p",
    ecdsa.curve_192,
    ecdsa.generator_192,
    (1, 2, 840, 10045, 3, 1, 1),
    "prime192v1",
)


NIST224p = Curve(
    "NIST224p",
    ecdsa.curve_224,
    ecdsa.generator_224,
    (1, 3, 132, 0, 33),
    "secp224r1",
)


NIST256p = Curve(
    "NIST256p",
    ecdsa.curve_256,
    ecdsa.generator_256,
    (1, 2, 840, 10045, 3, 1, 7),
    "prime256v1",
)


NIST384p = Curve(
    "NIST384p",
    ecdsa.curve_384,
    ecdsa.generator_384,
    (1, 3, 132, 0, 34),
    "secp384r1",
)


NIST521p = Curve(
    "NIST521p",
    ecdsa.curve_521,
    ecdsa.generator_521,
    (1, 3, 132, 0, 35),
    "secp521r1",
)


SECP256k1 = Curve(
    "SECP256k1",
    ecdsa.curve_secp256k1,
    ecdsa.generator_secp256k1,
    (1, 3, 132, 0, 10),
    "secp256k1",
)


BRAINPOOLP160r1 = Curve(
    "BRAINPOOLP160r1",
    ecdsa.curve_brainpoolp160r1,
    ecdsa.generator_brainpoolp160r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 1),
    "brainpoolP160r1",
)


BRAINPOOLP192r1 = Curve(
    "BRAINPOOLP192r1",
    ecdsa.curve_brainpoolp192r1,
    ecdsa.generator_brainpoolp192r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 3),
    "brainpoolP192r1",
)


BRAINPOOLP224r1 = Curve(
    "BRAINPOOLP224r1",
    ecdsa.curve_brainpoolp224r1,
    ecdsa.generator_brainpoolp224r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 5),
    "brainpoolP224r1",
)


BRAINPOOLP256r1 = Curve(
    "BRAINPOOLP256r1",
    ecdsa.curve_brainpoolp256r1,
    ecdsa.generator_brainpoolp256r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 7),
    "brainpoolP256r1",
)


BRAINPOOLP320r1 = Curve(
    "BRAINPOOLP320r1",
    ecdsa.curve_brainpoolp320r1,
    ecdsa.generator_brainpoolp320r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 9),
    "brainpoolP320r1",
)


BRAINPOOLP384r1 = Curve(
    "BRAINPOOLP384r1",
    ecdsa.curve_brainpoolp384r1,
    ecdsa.generator_brainpoolp384r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 11),
    "brainpoolP384r1",
)


BRAINPOOLP512r1 = Curve(
    "BRAINPOOLP512r1",
    ecdsa.curve_brainpoolp512r1,
    ecdsa.generator_brainpoolp512r1,
    (1, 3, 36, 3, 3, 2, 8, 1, 1, 13),
    "brainpoolP512r1",
)


# no order in particular, but keep previously added curves first
curves = [
    NIST192p,
    NIST224p,
    NIST256p,
    NIST384p,
    NIST521p,
    SECP256k1,
    BRAINPOOLP160r1,
    BRAINPOOLP192r1,
    BRAINPOOLP224r1,
    BRAINPOOLP256r1,
    BRAINPOOLP320r1,
    BRAINPOOLP384r1,
    BRAINPOOLP512r1,
    SECP112r1,
    SECP112r2,
    SECP128r1,
    SECP160r1,
]


def find_curve(oid_curve):
    for c in curves:
        if c.oid == oid_curve:
            return c
    raise UnknownCurveError(
        "I don't know about the curve with oid %s."
        "I only know about these: %s" % (oid_curve, [c.name for c in curves])
    )
