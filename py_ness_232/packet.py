import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class CommandType(Enum):
    SYSTEM_STATUS = 0x61
    USER_INTERFACE = 0x60


@dataclass
class Packet:
    address: Optional[int]
    seq: int
    command: CommandType
    data: str
    timestamp: Optional[datetime.datetime]

    # Whether or not this packet is a USER_INTERFACE response
    is_user_interface_resp: bool = False

    @property
    def start(self):
        rv = 0x02 | 0x80
        if self.address is not None and not self.is_user_interface_resp:
            rv |= 0x01
        if self.timestamp is not None:
            rv |= 0x04

        return rv

    @property
    def length_field(self):
        return int(self.length) | (self.seq << 7)

    @property
    def length(self) -> int:
        if is_user_interface_req(self.start):
            return len(self.data)
        else:
            return int(len(self.data) / 2)

    @property
    def checksum(self) -> int:
        bytes = self.encode(with_checksum=False)
        total = sum([ord(x) for x in bytes]) & 0xff
        return 256 - total

    def encode(self, with_checksum: bool = True) -> str:
        data = ''
        data += '{:02x}'.format(self.start)

        if self.address is not None:
            if is_user_interface_req(self.start):
                data += '{:01x}'.format(self.address)
            else:
                data += '{:02x}'.format(self.address)

        data += '{:02x}'.format(self.length_field)
        data += '{:02x}'.format(self.command.value)
        data += self.data
        if self.timestamp is not None:
            data += self.timestamp.strftime('%y%m%d%H%M%S')

        if with_checksum:
            data += '{:02x}'.format(self.checksum).upper()

        return data

    @classmethod
    def decode(cls, _data: str) -> 'Packet':
        """
        Packets are ASCII encoded data. Packet layout is as follows:

        +---------------------------------------------------------------------------+
        | start | address | length | command | data | timestamp | checksum | finish |
        | hex   | hex     | hex    | hex     | str  | dec       | hex      | crlf   |
        | 1     | 1       | 1      | 1       | n    | 6         | 1        |        |
        +---------------------------------------------------------------------------+

        Timestamp:
            Timestamps are formatted in the following format, where each field is
            decimal encoded:

            YY MM DD HH MM SS

        Checksum:
            Calculated by...?

        Since data is ASCII encoded, each byte uses 2 ASCII character to be
        represented. However, we cannot simply do a hex decode on the entire
        message, since the timestamp and data fields are represented using a
        non-hex representation and therefore must be manually decoded.
        """

        # TODO(NW): Figure out checksum validation
        # if not is_data_valid(_data.decode('ascii')):
        #     raise ValueError("Unable to decode: checksum verification failed")

        data = DataIterator(_data)
        _LOGGER.debug("Decoding bytes: '%s'", _data)

        start = data.take_hex()

        address = None
        if has_address(start):
            address = data.take_hex(half=is_user_interface_req(start))

        length = data.take_hex()
        data_length = length & 0x7f
        seq = length >> 7
        command = CommandType(data.take_hex())
        msg_data = data.take_bytes(data_length, half=is_user_interface_req(start))
        timestamp = None
        if has_timestamp(start):
            timestamp = decode_timestamp(data.take_bytes(6))

        checksum = data.take_hex()

        if not data.is_consumed():
            raise ValueError('Unable to consume all data')

        return Packet(
            is_user_interface_resp=is_user_interface_resp(start) and command == CommandType.USER_INTERFACE,
            address=address,
            seq=seq,
            command=command,
            data=msg_data,
            timestamp=timestamp,
        )


class DataIterator:
    def __init__(self, data: str):
        self._data = data
        self._position = 0

    def take_bytes(self, n, half=False) -> str:
        multi = 2 if not half else 1
        position = self._position
        self._position += n * multi
        if self._position > len(self._data):
            raise ValueError("Unable to take more data than exists")

        return self._data[position:self._position]

    def take_hex(self, half=False) -> int:
        return int(self.take_bytes(1, half), 16)

    def take_dec(self, half=False) -> int:
        return int(self.take_bytes(1, half), 10)

    def is_consumed(self):
        return self._position >= len(self._data)


def has_address(start: int) -> bool:
    return bool(0x01 & start) or start == 0x82


def has_timestamp(start: int) -> bool:
    return bool(0x04 & start)


def is_user_interface_req(start: int) -> bool:
    return start == 0x83


def is_user_interface_resp(start: int) -> bool:
    return start == 0x82


def decode_timestamp(data: str) -> datetime.datetime:
    return datetime.datetime.strptime(data, '%y%m%d%H%M%S')


def is_data_valid(data: str) -> bool:
    split_string = lambda x, n: [x[i:i + n] for i in range(0, len(x), n)]

    sum = 0
    for byte in split_string(data, 2):
        sum += int(byte, 16)

    return sum & 0xff == 0
