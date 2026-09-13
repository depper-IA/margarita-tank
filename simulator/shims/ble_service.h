#ifndef BLE_SERVICE_H
#define BLE_SERVICE_H

#include "notification.h"
#include <stdint.h>

#define MAX_VISIBLE_SESSIONS 4

/* Display status values sent by daemon via set_status action */
typedef enum {
    DISPLAY_STATUS_SLEEPING,
    DISPLAY_STATUS_IDLE,
    DISPLAY_STATUS_THINKING,
    DISPLAY_STATUS_WORKING_1,
    DISPLAY_STATUS_WORKING_2,
    DISPLAY_STATUS_WORKING_3,
    DISPLAY_STATUS_CONFUSED,
    DISPLAY_STATUS_SWEEPING,
} display_status_t;

typedef enum {
    BLE_EVT_NOTIF_ADD,
    BLE_EVT_NOTIF_DISMISS,
    BLE_EVT_NOTIF_CLEAR,
    BLE_EVT_SET_STATUS,
    BLE_EVT_SET_SESSIONS,
    BLE_EVT_SET_USAGE,
    BLE_EVT_CONNECTED,
    BLE_EVT_DISCONNECTED,
} ble_evt_type_t;

typedef struct {
    ble_evt_type_t type;
    char id[NOTIF_MAX_ID_LEN];
    char project[NOTIF_MAX_PROJ_LEN];
    char message[NOTIF_MAX_MSG_LEN];
    uint8_t status;  /* display_status_t, used only for BLE_EVT_SET_STATUS */
    /* set_sessions data (BLE_EVT_SET_SESSIONS) */
    uint8_t session_anim_count;
    uint8_t session_anims[MAX_VISIBLE_SESSIONS];
    uint16_t session_ids[MAX_VISIBLE_SESSIONS];
    uint8_t subagent_count;
    uint8_t session_overflow;
    uint8_t alert;  /* 0=none, 1=error */
    /* set_usage data (BLE_EVT_SET_USAGE) */
    int16_t usage_session_pct;   /* 5h window used %, -1 = unknown */
    int16_t usage_weekly_pct;    /* 7d window used %, -1 = unknown */
    int32_t usage_reset_s;       /* seconds until 5h reset, -1 = unknown */
} ble_evt_t;

/* Stub — simulator does not init real BLE */
static inline void ble_service_init(void *q) { (void)q; }

#endif
