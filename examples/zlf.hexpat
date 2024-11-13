#pragma author luthomas
// #pragme descrption ZLF (Binary DCH)

import std.mem;


bitfield PtiRadioConfig {
    z_wave_region_id: 5;
    reserved: 3; // these bits are always set to 0
};


bitfield PtiRadioInfo {
    channel_number: 6;
    is_syncword_selected: 1;
    is_antenna_selected: 1;
};


bitfield PtiStatus0 {
    protocol_id: 4;
    error_code: 4;
};

bitfield PtiAppendedInfoCfg {
    version: 3;
    length: 3;
    is_rx: 1;
    reserved: 1; // this bit is always set to 0
};

struct PtiAppendedInfoRx {
    s8 rssi;
    PtiRadioConfig pti_radio_config;
    PtiRadioInfo pti_radio_info;
    PtiStatus0 pti_status0;
    PtiAppendedInfoCfg pti_appended_info_cfg;
};

struct PtiAppendedInfoTx {
    PtiRadioConfig pti_radio_config;
    PtiRadioInfo pti_radio_info;
    PtiStatus0 pti_status0;
    PtiAppendedInfoCfg pti_appended_info_cfg;
};

struct DchV2Header {
    u8 timestamp_us[6];
    u16 type;
    u8 sequence_number;
};

struct DchV3Header {
    u64 timestamp_ns;
    u16 type;
    u32 flags;
    u16 sequence_number;
};

struct DchFrame {
    u8 start_symbol [[color("0000FF")]];
    u16 length [[color("FFFFFF")]];
    u16 version [[color("FFFFFF")]];
    if (version == 2) {
        DchV2Header header [[color("FFFFFF")]]; // TODO: check that the type is PTI
        u8 pti_hw_start [[color("FF0000")]];
        if (pti_hw_start == 0xF8) {
            // the -7 below is (hw_start + hw_stop + append_info (Rx))
            u8 pti_ota_payload[length - 13 -7] [[color("000000")]];
            u8 pti_hw_stop [[color("FF0000")]];
            PtiAppendedInfoRx pti_appended_info [[color("00FF00")]];
        } else if (pti_hw_start == 0xFC) {
            // the -6 below is (hw_start + hw_stop + append_info (T4x))
            u8 pti_ota_payload[length - 13 -6] [[color("000000")]];
            u8 pti_hw_stop [[color("FF0000")]];
            PtiAppendedInfoTx pti_appended_info [[color("00FF00")]];
        }
    }
    else if (version == 3) {
        DchV3Header header [[color("FFFFFF")]]; // TODO: check that the type is PTI
        u8 pti_hw_start [[color("FF0000")]];
        if (pti_hw_start == 0xF8) {
            // the -7 below is (hw_start + hw_stop + append_info (Rx))
            u8 pti_ota_payload[length - 20 -7] [[color("000000")]];
            u8 pti_hw_stop [[color("FF0000")]];
            PtiAppendedInfoRx pti_appended_info [[color("00FF00")]] ;
        } else if (pti_hw_start == 0xFC) {
            // the -6 below is (hw_start + hw_stop + append_info (T4x))
            u8 pti_ota_payload[length - 20 -6] [[color("000000")]];
            u8 pti_hw_stop [[color("FF0000")]];
            PtiAppendedInfoTx pti_appended_info [[color("00FF00")]];
        }
    }
    u8 stop_symbol [[color("0000FF")]];
};

struct DchPacket {
    DchFrame frame; // single frame for now, we'll see about more later
};

struct ZlfHeader {
    u8 header_data[2048];
};


bitfield ZlfDataChunkProperty {
   is_outcome: 1;
   session_id: 7; // may be inverted I did not check.
};

struct ZlfDataChunk {
    u64 timestamp [[color("FF00FF")]];
    ZlfDataChunkProperty property [[color("FF00FF")]];
    u32 length [[color("FF00FF")]];
    DchFrame dch_packet;
    u8 api_type [[color("FFFF00")]];
};

ZlfHeader header @ 0x00;
ZlfDataChunk datachunks[while(!std::mem::eof())] @ 0x800;