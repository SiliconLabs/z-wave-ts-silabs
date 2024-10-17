meta:
  id: zlf
  title: ZLF trace file
  file-extension: zlf
  license: CC0-1.0
  ks-version: 0.10
  endian: le
  bit-endian: le
doc: |
  ZLF is the Z-Wave Zniffer trace format
seq:
  - id: header
    size: 2048
  - id: datachunk
    type: data_chunk
    repeat: eos
types:
  data_chunk:
    seq:
      - id: timestamp
        size: 8
      - id: is_outcome
        type: b1
        # enum: tx_or_rx
      - id: session_id
        type: b7
      - id: length
        type: u4
      - id: data_entries
        type: dch_list
        size: length
      - id: api_type
        type: u1
  dch_list: # zlf specific horror
    seq:
      - id: dch_item
        type: dch
        repeat: eos
  dch:
    seq:
      - id: start_symbol
        type: u1
        valid: 0x5B
      - id: length
        type: u2
      - id: version
        type: u2
      - id: dch_specific_version
        type:
          switch-on: version
          cases:
            2: dch_v2(length)
            3: dch_v3(length)
      - id: stop_symbol
        type: u1
        valid: 0x5D
  dch_v2: # Data Channel Packet Format (V2)
    params:
      - id: length
        type: u2
    seq:
      - id: timestamp_us
        size: 6
      - id: type # 0x2a is PTI_RX
        type: u2
      - id: sequence_number
        type: u1
      - id: payload
        size: length - 13 # 13 is the DCHv2 Header minimum size (without payload)
        type: pti(length - 13)
  dch_v3: # Data Channel Packet Format (V3)
    params:
      - id: length
        type: u2
    seq:
      - id: timestamp_ns
        size: 8
      - id: type # 0x2a is PTI_RX
        type: u2
      - id: flags
        type: u4
      - id: sequence_number
        type: u2
      - id: payload
        size: length - 20 # 20 is the DCHv3 Header minimum size (without payload)
        type: pti(length - 20)
  # aem       : could be addded as well (only with DCH_v3)
  # PC Sample : could be addded as well (only with DCH_v3)
  # Exception : could be addded as well (only with DCH_v3)
  pti:
    instances:
      appended_info_inst:
        pos: _io.size - 5
        type: pti_appended_info
    params:
      - id: length
        type: u2
    seq:
      - id: hw_start # always starts with 0xF (0x0 - DMP Protocol Switch, 0x8 - Rx Start, 0xC - Tx Start)
        type: u1
      - id: ota_packet_data
        size: length - 7 # hw_start + hw_end + appended_info = 7 bytes (this should not change in Z-Wave)
        type: zwave_mac_frame(length - 7, appended_info_inst.zwave_region, appended_info_inst.channel_number)
        # type: zwave_mac_frame(length - 7)
      - id: hw_end # always starts with 0xF (0x9 - Rx Success, 0xA - Rx Abort, 0xD - Tx Success, 0xE - Tx Abort)
        type: u1
      - id: appended_info
        type: pti_appended_info
        # size: 5
  pti_appended_info:
    meta:
      bit-endian: be          # for parsing APPENDED_INFO bitfields
    seq:
      - id: rssi              # RSSI (1 signed byte)
        type: s1
      - id: zwave_region      # RADIO_CONFIG
        type: u1
      - id: antenna_selected  # RADIO_INFO
        type: b1
      - id: syncword_selected # RADIO_INFO
        type: b1
      - id: channel_number    # RADIO_INFO
        type: b6
      - id: error_code        # STATUS_0 (error for Z-Wave -> 0: Success, 1: CRC Failed or invalid packet length, 2: Dropped/Overflow, 4: ADDRESS_FILTERED, 11: ZWAVE_BEAM_ACCEPTED, 12: ZWAVE_BEAM_IGNORED, 14: USER_ABORT)
        type: b4
      - id: protocol_id       # STATUS_0
        type: b4
      - id: rx_or_tx          # APPENDED_INFO_CFG
        type: b2
      - id: length            # APPENDED_INFO_CFG (actual_length - 2)
        type: b3
      - id: version           # APPENDED_INFO_CFG
        type: b3

  zwave_mac_frame:
    params: # region and channel are RAIL/PHY specific, please check out what combinations to use to parse between: BASIC, BASIC24 and BASICLR
      - id: length
        type: u1
      - id: region
        type: u1
      - id: channel
        type: u1
    instances:
      has_beam_tag:
        pos: 0x00
        type: u1
    seq:
      - id: zwave_mac_frame_type
        type:
          switch-on: has_beam_tag
          cases:
            0x55: zwave_mac_frame_beam(length, region, channel)
            _: zwave_mac_frame_base(length, region, channel)

  zwave_mac_frame_base:
    # Z-Wave mac frame parsing depends on baud_rate of each channel for a given region. see: platform/radio/rail_lib/protocol/zwave/zwave_regions.json
    # Korea and Japan have an ENERGY_DETECT specific.
    # 17 regions in RAIL + Invalid at Index 0 but we should not parse it.
    # RAIL people are sane, this is refreshing coming from Z-Wave
    # in the channel config 1,2 regions and with LR regions (except end devices) the default is:
    # - ch0 -> 100k
    # - ch1 -> 40k  (CRC is on 1 byte)
    # - ch2 -> 9.6k (CRC is on 1 byte)
    # - ch3 -> 100k LR (Long range only) -> RAIL_ZWAVE_RegionId_t = 12, 13, 15 and 16
    # in the channel config 3 regions (Japan and Korea) -> RAIL_ZWAVE_RegionId_t = 7 and 10
    # - ch0 -> 100k
    # - ch1 -> 100k
    # - ch2 -> 100k
    # in the case of EU_LR_END_DEVICE and US_LR_END_DEVICE -> RAIL_ZWAVE_RegionId_t = 14 and 17
    # - ch0 -> 100k LR
    # - ch1 -> 100k LR    
    params:
      - id: length
        type: u1
      - id: region
        type: u1
      - id: channel
        type: u1
    instances:
      region_mod:
        # hack to get US_LR1, US_LR_2, EU_LR_1, EU_LR_2 to be treated as LR mac frames
        # in RAIL these regions are the only ones to have 4 channels, the last one (3)
        # being reserved for either LR channel A or B (1 or 2).
        # 14 is the ID of US_LR_END_DEVICE (it could have been EU_LR_END_DEVICE instead)
        value: channel == 3 ? 14 : region
    seq:
      - id: home_id
        size: 4
      - id: zwave_mac_frame_header_type
        type:
          switch-on: region_mod
          cases:
            7: zwave_mac_frame_classic_3ch      # JP
            10: zwave_mac_frame_classic_3ch     # KR
            14: zwave_mac_frame_lr              # US_LR_END_DEVICE
            17: zwave_mac_frame_lr              # EU_LR_END_DEVICE
            _: zwave_mac_frame_classic(channel) # the rest of the regions

  zwave_mac_frame_classic:
    meta:
      bit-endian: be
    params:
      - id: channel
        type: u1
    seq:
      - id: src_node_id
        type: u1
      - id: header_type
        type: b4
      - id: speed_modifier
        type: b1
      - id: low_power
        type: b1
      - id: ack
        type: b1
      - id: routed
        type: b1
      - id: sequence_number
        type: b4
      - id: reserved
        type: b1
      - id: source_wakeup_beam_250ms # why are source and wakeup inverted in this name ?
        type: b1
      - id: wakeup_source_beam_1000ms # why are source and wakeup inverted in this name ?
        type: b1
      - id: suc_present
        type: b1
      - id: length
        type: u1
      - id: dst_node_id
        type: u1
      # - id: routing_header
      #   type: zwave_nwk_header
      - id: payload
        size: 0 # TODO
      - id: crc
        type:
          switch-on: channel
          cases:
            0: u1 # ch0 (9.6k)
            1: u1 # ch1 (40k)
            2: u2 # ch2 (100k)
            _: u1 # default to 1 byte just in case

  zwave_mac_frame_classic_3ch:
    meta:
      bit-endian: be
    seq:
      - id: src_node_id
        type: u1
      - id: header_type
        type: b4
      - id: speed_modifier
        type: b1
      - id: suc_present
        type: b1
      - id: low_power
        type: b1
      - id: ack
        type: b1
      - id: reserved
        type: b4
      - id: source_wakeup
        type: b3
      - id: extended
        type: b1
      - id: length
        type: u1
      - id: sequence_number
        type: u1
      - id: dst_node_id
        type: u1
      # - id: routing_header
      #   type: zwave_nwk_header
      - id: payload
        size: 0 # TODO
      - id: crc
        type: u2

  zwave_mac_frame_lr:
    meta:
      bit-endian: be
    seq:
      - id: src_node_id
        type: b12
      - id: dst_node_id
        type: b12
      - id: length
        type: u1
      - id: header_type
        type: b3
      - id: low_power # or reserved ?
        type: b3
      - id: extended
        type: b1
      - id: ack
        type: b1
      - id: sequence_number
        type: u1
      - id: noise_floor
        type: u1
      - id: tx_power
        type: u1
      # there's another property here normally ?
      - id: payload
        size: 0 # TODO
      - id: crc
        type: u2

  zwave_mac_frame_beam:
    params:
      - id: length
        type: u1
      - id: region
        type: u1
      - id: channel
        type: u1
    instances:
      region_mod:
        # hack to get US_LR1, US_LR_2, EU_LR_1, EU_LR_2 to be treated as LR mac frames
        # in RAIL these regions are the only ones to have 4 channels, the last one (3)
        # being reserved for either LR channel A or B (1 or 2).
        # 14 is the ID of US_LR_END_DEVICE (it could have been EU_LR_END_DEVICE instead)
        value: channel == 3 ? 14 : region
    seq:
      - id: beam_tag
        type: u1
        valid: 0x55
      - id: zwave_mac_frame_beam_type
        type:
          switch-on: region_mod
          cases:
            14: zwave_mac_frame_beam_lr             # US_LR_END_DEVICE
            17: zwave_mac_frame_beam_lr             # EU_LR_END_DEVICE
            _: zwave_mac_frame_beam_classic(length) # the rest of the regions
  
  zwave_mac_frame_beam_classic:
    params:
      - id: length
        type: u1
    seq:
      - id: dst_node_id
        type: u1
      - id: home_id_hash
        type: u1
        if: length > 2 # in JP (and maybe in KR too ?) the home_id_hash is not included.
  
  zwave_mac_frame_beam_lr:
    seq:
      - id: dst_node_id
        type: b12
      - id: tx_power
        type: b4
      - id: home_id_hash
        type: u1

  zwave_nwk_header:
    params:
      - id: region
        type: u1
    seq:
      - id: todo
        size: 0
  
  zwave_explore_header:
    seq:
      - id: todo
        size: 0

# instances:
#   api_type_converted:
#     value: 254 - data_chunk.api_type
    # enum: frame_type
# enums:
  # tx_or_rx:
  #   0: RX
  #   1: TX
  # frame_type:
  #   0: 500sZniffer
  #   1: SerialAPI
  #   2: 500sProgrammer
  #   3: ZIPGW
  #   4: Reserved
  #   5: Reserved
  #   6: Attachment
  #   7: Text
  #   8: XModem
  #   9: PTI
  #   10: PTIDiagnostic
  #   11: UIC
  #   128: WstkInstrument
  #   129: AttenuatorRudatInstrument
  #   139: PsuE364xInstrument
  #   131: Dmm7510Instrument
