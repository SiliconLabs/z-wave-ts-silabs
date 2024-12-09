#pragma description pcap header and packets

import std.mem;
#pragma MIME application/vnd.tcpdump.pcap

enum network_type : u32 {
    LINKTYPE_NULL = 0,
    LINKTYPE_ETHERNET = 1,
    LINKTYPE_AX25 = 3,
    LINKTYPE_IEEE802_5 = 6,
    LINKTYPE_ARCNET_BSD = 7,
    LINKTYPE_SLIP = 8,
    LINKTYPE_PPP = 9,
    LINKTYPE_FDDI = 10,
    LINKTYPE_PPP_HDLC = 50,
    LINKTYPE_PPP_ETHER = 51,
    LINKTYPE_ATM_RFC1483 = 100,
    LINKTYPE_RAW = 101,
    LINKTYPE_C_HDLC = 104,
    LINKTYPE_IEEE802_11 = 105,
    LINKTYPE_FRELAY = 107,
    LINKTYPE_LOOP = 108,
    LINKTYPE_LINUX_SLL = 113,
    LINKTYPE_LTALK = 114,
    LINKTYPE_PFLOG = 117,
    LINKTYPE_IEEE802_11_PRISM = 119,
    LINKTYPE_IP_OVER_FC = 122,
    LINKTYPE_SUNATM = 123,
    LINKTYPE_IEEE802_11_RADIOTAP = 127,
    LINKTYPE_ARCNET_LINUX = 129,
    LINKTYPE_APPLE_IP_OVER_IEEE1394 = 138,
    LINKTYPE_MTP2_WITH_PHDR = 139,
    LINKTYPE_MTP2 = 140,
    LINKTYPE_MTP3 = 141,
    LINKTYPE_SCCP = 142,
    LINKTYPE_DOCSIS = 143,
    LINKTYPE_LINUX_IRDA = 144,
    LINKTYPE_IEEE802_11_AVS = 163,
    LINKTYPE_BACNET_MS_TP = 165,
    LINKTYPE_PPP_PPPD = 166,
    LINKTYPE_GPRS_LLC = 169,
    LINKTYPE_GPF_T = 170,
    LINKTYPE_GPF_F = 171,
    LINKTYPE_LINUX_LAPD = 177,
    LINKTYPE_MFR = 182,
    LINKTYPE_BLUETOOTH_HCI_H4 = 187,
    LINKTYPE_USB_LINUX = 189,
    LINKTYPE_PPI = 192,
    LINKTYPE_IEEE802_15_4_WITHFCS = 195,
    LINKTYPE_SITA = 196,
    LINKTYPE_ERF = 197,
    LINKTYPE_BLUETOOTH_HCI_H4_WITH_PHDR = 201,
    LINKTYPE_AX25_KISS = 202,
    LINKTYPE_LAPD = 203,
    LINKTYPE_PPP_WITH_DIR = 204,
    LINKTYPE_C_HDLC_WITH_DIR = 205,
    LINKTYPE_FRELAY_WITH_DIR = 206,
    LINKTYPE_LAPB_WITH_DIR = 207,
    LINKTYPE_IPMB_LINUX = 209,
    LINKTYPE_FLEXRAY = 210,
    LINKTYPE_IEEE802_15_4_NONASK_PHY = 215,
    LINKTYPE_USB_LINUX_MMAPPED = 220,
    LINKTYPE_FC_2 = 224,
    LINKTYPE_FC_2_WITH_FRAME_DELIMS = 225,
    LINKTYPE_IPNET = 226,
    LINKTYPE_CAN_SOCKETCAN = 227,
    LINKTYPE_IPV4 = 228,
    LINKTYPE_IPV6 = 229,
    LINKTYPE_IEEE802_15_4_NOFCS = 230,
    LINKTYPE_DBUS = 231,
    LINKTYPE_DVB_CI = 235,
    LINKTYPE_MUX27010 = 236,
    LINKTYPE_STANAG_5066_D_PDU = 237,
    LINKTYPE_NFLOG = 239,
    LINKTYPE_NETANALYZER = 240,
    LINKTYPE_NETANALYZER_TRANSPARENT = 241,
    LINKTYPE_IPOIB = 242,
    LINKTYPE_MPEG_2_TS = 243,
    LINKTYPE_NG40 = 244,
    LINKTYPE_NFC_LLCP = 245,
    LINKTYPE_INFINIBAND = 247,
    LINKTYPE_SCTP = 248,
    LINKTYPE_USBPCAP = 249,
    LINKTYPE_RTAC_SERIAL = 250,
    LINKTYPE_BLUETOOTH_LE_LL = 251,
    LINKTYPE_NETLINK = 253,
    LINKTYPE_BLUETOOTH_LINUX_MONITOR = 254,
    LINKTYPE_BLUETOOTH_BREDR_BB = 255,
    LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR = 256,
    LINKTYPE_PROFIBUS_DL = 257,
    LINKTYPE_PKTAP = 258,
    LINKTYPE_EPON = 259,
    LINKTYPE_IPMI_HPM_2 = 260,
    LINKTYPE_ZWAVE_R1_R2 = 261,
    LINKTYPE_ZWAVE_R3 = 262,
    LINKTYPE_WATTSTOPPER_DLM = 263,
    LINKTYPE_ISO_14443 = 264,
    LINKTYPE_RDS = 265,
    LINKTYPE_USB_DARWIN = 266,
    LINKTYPE_SDLC = 268,
    LINKTYPE_LORATAP = 270,
    LINKTYPE_VSOCK = 271,
    LINKTYPE_NORDIC_BLE = 272,
    LINKTYPE_DOCSIS31_XRA31 = 273,
    LINKTYPE_ETHERNET_MPACKET = 274,
    LINKTYPE_DISPLAYPORT_AUX = 275,
    LINKTYPE_LINUX_SLL2 = 276,
    LINKTYPE_OPENVIZSLA = 278,
    LINKTYPE_EBHSCR = 279,
    LINKTYPE_VPP_DISPATCH = 280,
    LINKTYPE_DSA_TAG_BRCM = 281,
    LINKTYPE_DSA_TAG_BRCM_PREPEND = 282,
    LINKTYPE_IEEE802_15_4_TAP = 283,
    LINKTYPE_DSA_TAG_DSA = 284,
    LINKTYPE_DSA_TAG_EDSA = 285,
    LINKTYPE_ELEE = 286,
    LINKTYPE_Z_WAVE_SERIAL = 287,
    LINKTYPE_USB_2_0 = 288,
    LINKTYPE_ATSC_ALP = 289,
    LINKTYPE_ETW = 290
};

enum magic : u32 {
	BE = 0xA1B2C3D4,
	LE = 0xD4C3B2A1
};

// TODO: parse frame_control for both so that singlecast and multicast mhr can be parsed in both
// otherwise mhr would have to be splitted between mhr_base and mhr_singlecast and mhr_multicast
// in this langage we can have both in one structure and it's better like that IMO.

bitfield z_wave_frame_control_ch_1_2_t {
    header_type: 4;
    speed_modified: 1;
    low_power: 1;
    ack_req: 1;
    routed: 1;
    sequence_number: 4;
    reserved_2: 1;
    beaming_info: 2;
    reserved_1: 1;
};

bitfield z_wave_frame_control_ch_3_t {
    header_type: 4;
    reserved_1: 2;
    low_power: 1;
    ack_req: 1;
    reserved_3: 4;
    beaming_info: 3;
    reserved_2: 1;
};

struct z_wave_classic_mhr_ch_1_2_t {
    u32 home_id;
    u8 src_node_id;
    z_wave_frame_control_ch_1_2_t frame_control;
    u8 length;
    if (frame_control.header_type == 0x02) { // multicast
        u8 multicast_control;
        u8 multicast_bit_mask[29];
    } else { // singlecast
        u8 dst_node_id;
    }
};

struct z_wave_classic_mhr_ch_3_t {
    u32 home_id;
    u8 src_node_id;
    z_wave_frame_control_ch_3_t frame_control;
    u8 length;
    u8 sequence_number;
    if (frame_control.header_type == 0x02) { // multicast
        u8 multicast_control;
        u8 multicast_bit_mask[29];
    } else { // singlecast
        u8 dst_node_id;
    }
};

//TODO: LR

struct z_wave_tap_header_t {
    u8 tap_header_version;
    u8 tap_header_reserved;
    u16 tap_header_length;
};

struct z_wave_tap_tlv_fcs_t {
    u16 tlv_type [[color("0000FF")]]; // type = 0
    u16 tlv_length [[color("0000FF")]];
    u8 fcs_type [[color("FF0000")]]; // 0 = Reserved, 1 = 8-bit non-correcting FCS (R1 and R2), 2 = 16 bit CRC-CCITT (R3)
    u8 _padding[3];
};

struct z_wave_tap_tlv_rss_t {
    u16 tlv_type [[color("0000FF")]]; // type = 1
    u16 tlv_length [[color("0000FF")]];
    s32 dbm [[color("FF0000")]];
};

struct z_wave_tap_tlv_rf_info_t {
    u16 tlv_type [[color("0000FF")]]; // type = 2
    u16 tlv_length [[color("0000FF")]];
    u16 region [[color("FF0000")]];
    u16 data_rate [[color("FF0000")]];
    u32 frequency_in_khz [[color("FF0000")]];
};

fn zwave_payload_length(u16 region, u16 data_rate, u8 header_type, u8 mpdu_length) {
    u8 length = mpdu_length;

    if (header_type == 0x02) {
        length -= 29; // multicast bit mask size
    }

    // TODO: add LR
    if (region == 7 || region == 9) {
        length -= 10; // 4 + 1 + 2 + 1 + (1) + 1
    } else {
        length -= 9;// 4 + 1 + 2 + 1 + 1
    }


    if (data_rate == 3) {
        length -= 2; // CRC is 2 bytes
    } else {
        length -= 1; // CRC is 1 byte
    }

    return length;
};

struct pcap_record_t {
    u32 ts_sec [[color("FFFFFF")]];         /* timestamp seconds */
    u32 ts_usec [[color("FF00FF")]];        /* timestamp microseconds */
    u32 incl_len [[color("FFFFFF")]];       /* number of octets of packet saved in file */
    u32 orig_len [[color("FF00FF")]];       /* actual length of packet */
    // the whole TAP header and TLVs is 32 bytes in length.
    z_wave_tap_header_t tap_header [[color("00FF00")]];
    z_wave_tap_tlv_fcs_t tlv_fcs;
    z_wave_tap_tlv_rss_t tlv_rss;
    z_wave_tap_tlv_rf_info_t tlv_rf_info;
    // Z-Wave MAC frames layout is different depending on the region.
    // u8 payload[orig_len - 32] [[color("000000")]];
    if (tlv_rf_info.region == 7 || tlv_rf_info.region == 9) { // channel config 3
        z_wave_classic_mhr_ch_3_t zwave_mhr [[color("000000")]];
    } else if (tlv_rf_info.region > 11) { // LR
        z_wave_classic_mhr_ch_3_t zwave_mhr [[color("000000")]];
    } else { // channel config 1 and 2
        z_wave_classic_mhr_ch_1_2_t zwave_mhr [[color("000000")]];
    }
    u8 payload[zwave_payload_length(tlv_rf_info.region, tlv_rf_info.data_rate, zwave_mhr.frame_control.header_type, zwave_mhr.length)] [[color("000000")]];
    if (tlv_rf_info.data_rate == 3) { // CRC is 2 bytes
        u16 crc [[color("000000")]];
    } else {
        u8 crc [[color("000000")]];
    }
};

struct pcap_header_t {
    u16 version_major;    /* major version number */
    u16 version_minor;    /* minor version number */
    s32 thiszone;         /* GMT to local correction */
    u32 sigfigs;          /* accuracy of timestamps */
    u32 snaplen;          /* max length of captured packets, in octets */
    network_type network; /* data link type */
};

struct pcap {
    be magic magic_number;
    if (magic_number == magic::BE) {
        be pcap_header_t header;
        be pcap_record_t packet[while(!std::mem::eof())];
    } else {
        le pcap_header_t header;
        le pcap_record_t packet[while(!std::mem::eof())];
    }
};

pcap pcap @ 0x00;
