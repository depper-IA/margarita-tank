#include "notification_ui.h"
#include <string.h>
#include <stdio.h>

/* ---------- Constants ---------- */

#define SCREEN_W              320
#define SCREEN_H              172
#define COUNTER_H             20
#define FEATURED_H            64
#define FEATURED_H_EXPANDED   (SCREEN_H - COUNTER_H - 8)  /* fills panel on new notif */
#define COMPACT_ROW_H         14
#define DOT_SIZE              6

/* How long the expanded "hero" view is shown before shrinking to compact list */
#define EXPAND_HOLD_MS        2500
/* Duration of the shrink animation from expanded → compact */
#define EXPAND_ANIM_MS        350

/* Accent colors per notification slot (1:1 mapping, max 8) */
static const uint32_t accent_colors[NOTIF_MAX_COUNT] = {
    0xff6b2b, 0x4488ff, 0xaaaa33, 0x44aa44,
    0x7b68ee, 0x44cccc, 0xcc4488, 0xccaa22,
};

/* ---------- Auto-rotation ---------- */

#define ROTATION_INTERVAL_MS 8000

/* ---------- Struct ---------- */

struct notification_ui_t {
    lv_obj_t *container;

    /* Counter header */
    lv_obj_t *counter_label;

    /* Featured card */
    lv_obj_t *featured_card;
    lv_obj_t *featured_project;
    lv_obj_t *featured_message;
    lv_obj_t *featured_badge;

    /* Compact list entries */
    lv_obj_t *compact_rows[NOTIF_MAX_COUNT];
    int compact_count;

    /* Sorted notification cache */
    notification_t sorted[NOTIF_MAX_COUNT];
    int sorted_count;

    /* Auto-rotation */
    int featured_idx;     /* index into sorted[] currently featured */
    lv_timer_t *rotation_timer;

    /* Expand/collapse transition */
    bool featured_expanded;       /* true while in hero/expanded view */
    lv_timer_t *expand_hold_timer; /* fires after EXPAND_HOLD_MS to collapse */
};

/* ---------- Forward declarations ---------- */

static void rotation_timer_cb(lv_timer_t *timer);
static void rebuild_display(notification_ui_t *ui);
static void fade_anim_cb(void *var, int32_t val);
static void fade_hide_completed_cb(lv_anim_t *a);
static void expand_hold_timer_cb(lv_timer_t *timer);
static void featured_height_anim_cb(void *var, int32_t val);
static void collapse_completed_cb(lv_anim_t *a);
static void start_collapse_anim(notification_ui_t *ui);

/* ---------- Create ---------- */

notification_ui_t *notification_ui_create(lv_obj_t *parent)
{
    notification_ui_t *ui = lv_malloc_zeroed(sizeof(notification_ui_t));
    if (!ui) return NULL;

    /* Container — full height, positioned by set_x */
    ui->container = lv_obj_create(parent);
    lv_obj_remove_style_all(ui->container);
    lv_obj_set_size(ui->container, SCREEN_W - 107, SCREEN_H);
    lv_obj_set_pos(ui->container, 107, 0);
    lv_obj_set_scrollbar_mode(ui->container, LV_SCROLLBAR_MODE_OFF);
    lv_obj_clear_flag(ui->container, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ui->container, LV_OBJ_FLAG_HIDDEN);

    /* Dark background matching the scene panel */
    lv_obj_set_style_bg_opa(ui->container, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(ui->container, lv_color_hex(0x0f1320), 0);

    /* Counter label: "> N WAITING!" */
    ui->counter_label = lv_label_create(ui->container);
    lv_obj_set_style_text_font(ui->counter_label, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(ui->counter_label, lv_color_hex(0xffdd57), 0);
    lv_obj_set_pos(ui->counter_label, 4, 2);
    lv_label_set_text(ui->counter_label, "");

    /* Featured card */
    ui->featured_card = lv_obj_create(ui->container);
    lv_obj_remove_style_all(ui->featured_card);
    lv_obj_set_style_bg_opa(ui->featured_card, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(ui->featured_card, lv_color_hex(0x2a1a3e), 0);
    lv_obj_set_style_border_width(ui->featured_card, 2, 0);
    lv_obj_set_style_border_color(ui->featured_card, lv_color_hex(accent_colors[0]), 0);
    lv_obj_set_style_radius(ui->featured_card, 3, 0);
    lv_obj_set_style_pad_all(ui->featured_card, 6, 0);
    lv_obj_set_pos(ui->featured_card, 4, COUNTER_H + 2);
    lv_obj_set_size(ui->featured_card, lv_pct(95), FEATURED_H);
    lv_obj_set_scrollbar_mode(ui->featured_card, LV_SCROLLBAR_MODE_OFF);
    lv_obj_clear_flag(ui->featured_card, LV_OBJ_FLAG_SCROLLABLE);

    /* Featured: project name — marquee scroll when text overflows */
    ui->featured_project = lv_label_create(ui->featured_card);
    lv_obj_set_style_text_font(ui->featured_project, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(ui->featured_project, lv_color_hex(0xffdd57), 0);
    lv_obj_set_pos(ui->featured_project, 0, 0);
    lv_label_set_long_mode(ui->featured_project, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_obj_set_width(ui->featured_project, lv_pct(100));

    /* Featured: message — marquee scroll when text overflows */
    ui->featured_message = lv_label_create(ui->featured_card);
    lv_obj_set_style_text_font(ui->featured_message, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->featured_message, lv_color_hex(0xcc99ff), 0);
    lv_obj_set_pos(ui->featured_message, 0, 18);
    lv_label_set_long_mode(ui->featured_message, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_obj_set_width(ui->featured_message, lv_pct(100));

    /* Featured: badge */
    ui->featured_badge = lv_label_create(ui->featured_card);
    lv_obj_set_style_text_font(ui->featured_badge, &lv_font_montserrat_10, 0);
    lv_obj_set_style_text_color(ui->featured_badge, lv_color_hex(0x88cc88), 0);
    lv_obj_set_pos(ui->featured_badge, 0, 38);

    /* Auto-rotation timer */
    ui->rotation_timer = lv_timer_create(rotation_timer_cb, ROTATION_INTERVAL_MS, ui);
    lv_timer_pause(ui->rotation_timer);

    /* Expand-hold timer — fires once after the hero view, then collapses.
     * auto_delete=false so we can re-use it on every new notification. */
    ui->expand_hold_timer = lv_timer_create(expand_hold_timer_cb, EXPAND_HOLD_MS, ui);
    lv_timer_set_repeat_count(ui->expand_hold_timer, 1);
    lv_timer_set_auto_delete(ui->expand_hold_timer, false);
    lv_timer_pause(ui->expand_hold_timer);

    ui->sorted_count = 0;
    ui->featured_idx = 0;
    ui->compact_count = 0;
    ui->featured_expanded = false;

    return ui;
}

/* ---------- Show/Hide ---------- */

void notification_ui_show(notification_ui_t *ui, bool show, int anim_ms)
{
    if (!ui) return;

    if (show) {
        lv_obj_clear_flag(ui->container, LV_OBJ_FLAG_HIDDEN);
        /* Rotation timer is resumed by collapse_completed_cb or rebuild;
         * don't resume it here while in expanded hero view. */
        if (ui->sorted_count > 1 && !ui->featured_expanded) {
            lv_timer_resume(ui->rotation_timer);
        }

        if (anim_ms > 0) {
            /* Fade in: transparent → opaque */
            lv_obj_set_style_opa(ui->container, LV_OPA_TRANSP, LV_PART_MAIN);
            lv_anim_t a;
            lv_anim_init(&a);
            lv_anim_set_var(&a, ui->container);
            lv_anim_set_values(&a, LV_OPA_TRANSP, LV_OPA_COVER);
            lv_anim_set_duration(&a, anim_ms);
            lv_anim_set_exec_cb(&a, fade_anim_cb);
            lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
            lv_anim_start(&a);
        } else {
            lv_obj_set_style_opa(ui->container, LV_OPA_COVER, LV_PART_MAIN);
        }
    } else {
        lv_timer_pause(ui->rotation_timer);
        lv_timer_pause(ui->expand_hold_timer);

        /* Cancel any in-flight hero collapse animation */
        lv_anim_delete(ui->featured_card, featured_height_anim_cb);
        ui->featured_expanded = false;

        if (anim_ms > 0) {
            /* Fade out: opaque → transparent, then hide */
            lv_anim_t a;
            lv_anim_init(&a);
            lv_anim_set_var(&a, ui->container);
            lv_anim_set_values(&a, LV_OPA_COVER, LV_OPA_TRANSP);
            lv_anim_set_duration(&a, anim_ms);
            lv_anim_set_exec_cb(&a, fade_anim_cb);
            lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
            lv_anim_set_completed_cb(&a, fade_hide_completed_cb);
            lv_anim_start(&a);
        } else {
            lv_obj_set_style_opa(ui->container, LV_OPA_COVER, LV_PART_MAIN);
            lv_obj_add_flag(ui->container, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

/* ---------- Fade animation callbacks ---------- */

static void fade_anim_cb(void *var, int32_t val)
{
    lv_obj_set_style_opa((lv_obj_t *)var, (lv_opa_t)val, LV_PART_MAIN);
}

static void fade_hide_completed_cb(lv_anim_t *a)
{
    lv_obj_t *obj = (lv_obj_t *)a->var;
    lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
    /* Reset opacity so the next fade-in starts clean */
    lv_obj_set_style_opa(obj, LV_OPA_COVER, LV_PART_MAIN);
}

/* ---------- Expand/collapse animation ---------- */

/* Animates featured_card height */
static void featured_height_anim_cb(void *var, int32_t val)
{
    lv_obj_set_height((lv_obj_t *)var, val);
}

/* Called when the shrink animation completes — show compact rows */
static void collapse_completed_cb(lv_anim_t *a)
{
    notification_ui_t *ui = (notification_ui_t *)a->user_data;
    if (!ui) return;

    ui->featured_expanded = false;

    /* Make compact rows visible by rebuilding at normal height */
    rebuild_display(ui);

    /* Resume auto-rotation now that both featured + compact are visible */
    if (ui->sorted_count > 1) {
        lv_timer_reset(ui->rotation_timer);
        lv_timer_resume(ui->rotation_timer);
    }
}

/* Animate the featured card from FEATURED_H_EXPANDED → FEATURED_H */
static void start_collapse_anim(notification_ui_t *ui)
{
    if (!ui || !ui->featured_expanded) return;

    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, ui->featured_card);
    lv_anim_set_values(&a, FEATURED_H_EXPANDED, FEATURED_H);
    lv_anim_set_duration(&a, EXPAND_ANIM_MS);
    lv_anim_set_exec_cb(&a, featured_height_anim_cb);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_in_out);
    lv_anim_set_user_data(&a, ui);
    lv_anim_set_completed_cb(&a, collapse_completed_cb);
    lv_anim_start(&a);
}

/* One-shot timer callback — fires after EXPAND_HOLD_MS to start collapse */
static void expand_hold_timer_cb(lv_timer_t *timer)
{
    notification_ui_t *ui = (notification_ui_t *)lv_timer_get_user_data(timer);
    if (!ui) return;
    start_collapse_anim(ui);
}

/* ---------- Position tracking ---------- */

void notification_ui_set_x(notification_ui_t *ui, int x_px)
{
    if (!ui) return;
    lv_obj_set_pos(ui->container, x_px, 0);
    lv_obj_set_width(ui->container, SCREEN_W - x_px);
}

/* ---------- Rebuild from store ---------- */

void notification_ui_rebuild(notification_ui_t *ui, const notification_store_t *store)
{
    if (!ui || !store) return;

    /* Collect active notifications */
    ui->sorted_count = 0;
    for (int i = 0; i < NOTIF_MAX_COUNT; i++) {
        if (store->items[i].active) {
            ui->sorted[ui->sorted_count++] = store->items[i];
        }
    }

    /* Sort by seq ascending (insertion sort, max 8 elements) */
    for (int i = 1; i < ui->sorted_count; i++) {
        notification_t tmp = ui->sorted[i];
        int j = i - 1;
        while (j >= 0 && ui->sorted[j].seq > tmp.seq) {
            ui->sorted[j + 1] = ui->sorted[j];
            j--;
        }
        ui->sorted[j + 1] = tmp;
    }

    /* Featured = newest (highest seq = last in sorted array) */
    ui->featured_idx = ui->sorted_count > 0 ? ui->sorted_count - 1 : 0;

    /* Manage rotation timer — suppress during hero/expanded view */
    if (ui->sorted_count > 1 && !ui->featured_expanded) {
        lv_timer_reset(ui->rotation_timer);
        lv_timer_resume(ui->rotation_timer);
    } else {
        lv_timer_pause(ui->rotation_timer);
    }

    rebuild_display(ui);
}

/* ---------- Hero (expanded) view trigger ---------- */

void notification_ui_trigger_hero(notification_ui_t *ui)
{
    if (!ui) return;
    if (ui->sorted_count == 0) return;

    /* Cancel any in-flight collapse animation for the featured card */
    lv_anim_delete(ui->featured_card, featured_height_anim_cb);

    /* Enter expanded state and re-draw immediately */
    ui->featured_expanded = true;
    lv_timer_pause(ui->rotation_timer);
    rebuild_display(ui);

    /* (Re)start the hold timer.
     * Restore repeat_count=1 in case it was consumed by a prior fire,
     * then reset the elapsed period and resume. */
    lv_timer_set_repeat_count(ui->expand_hold_timer, 1);
    lv_timer_reset(ui->expand_hold_timer);
    lv_timer_resume(ui->expand_hold_timer);
}

/* ---------- Internal: rebuild LVGL widgets ---------- */

static void rebuild_display(notification_ui_t *ui)
{
    int count = ui->sorted_count;

    if (count == 0) {
        lv_label_set_text(ui->counter_label, "");
        lv_obj_add_flag(ui->featured_card, LV_OBJ_FLAG_HIDDEN);
        /* Remove compact rows */
        for (int i = 0; i < ui->compact_count; i++) {
            if (ui->compact_rows[i]) {
                lv_obj_delete(ui->compact_rows[i]);
                ui->compact_rows[i] = NULL;
            }
        }
        ui->compact_count = 0;
        return;
    }

    int fi = ui->featured_idx;
    if (fi >= count) fi = count - 1;

    /* ---- Expanded hero mode: large featured card, no compact list ---- */
    if (ui->featured_expanded) {
        lv_label_set_text(ui->counter_label, "> NUEVO!");
        lv_obj_set_style_text_color(ui->counter_label,
                                    lv_color_hex(0xff6b6b), 0);

        lv_obj_clear_flag(ui->featured_card, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_height(ui->featured_card, FEATURED_H_EXPANDED);

        int color_idx = fi % NOTIF_MAX_COUNT;
        lv_obj_set_style_border_color(ui->featured_card,
                                      lv_color_hex(accent_colors[color_idx]), 0);
        lv_label_set_text(ui->featured_project, ui->sorted[fi].project);
        lv_label_set_text(ui->featured_message, ui->sorted[fi].message);

        /* In hero view, show a prominent "NEW" badge lower in the card */
        lv_obj_set_pos(ui->featured_badge, 0, FEATURED_H_EXPANDED - 24);
        lv_label_set_text(ui->featured_badge, "NUEVO");
        lv_obj_set_style_text_color(ui->featured_badge,
                                    lv_color_hex(0xff6b6b), 0);

        /* Remove any stale compact rows (e.g. from a prior rebuild) */
        for (int i = 0; i < ui->compact_count; i++) {
            if (ui->compact_rows[i]) {
                lv_obj_delete(ui->compact_rows[i]);
                ui->compact_rows[i] = NULL;
            }
        }
        ui->compact_count = 0;
        return;
    }

    /* ---- Normal / compact mode ---- */

    /* Counter: restore normal yellow color */
    lv_obj_set_style_text_color(ui->counter_label,
                                lv_color_hex(0xffdd57), 0);
    char counter_buf[24];
    snprintf(counter_buf, sizeof(counter_buf), "> %d ESPERANDO!", count);
    lv_label_set_text(ui->counter_label, counter_buf);

    /* Featured card at normal height */
    lv_obj_clear_flag(ui->featured_card, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_height(ui->featured_card, FEATURED_H);

    int color_idx = fi % NOTIF_MAX_COUNT;
    lv_obj_set_style_border_color(ui->featured_card,
                                  lv_color_hex(accent_colors[color_idx]), 0);

    /* Set full text — SCROLL_CIRCULAR mode will marquee if it overflows */
    lv_label_set_text(ui->featured_project, ui->sorted[fi].project);
    lv_label_set_text(ui->featured_message, ui->sorted[fi].message);

    /* Badge: NEWEST for highest-seq, index label for rotation */
    lv_obj_set_pos(ui->featured_badge, 0, 38);
    bool is_newest = (fi == count - 1);
    if (is_newest) {
        lv_label_set_text(ui->featured_badge, "RECIENTE");
        lv_obj_set_style_text_color(ui->featured_badge,
                                    lv_color_hex(0x88cc88), 0);
    } else {
        char badge_buf[24];
        snprintf(badge_buf, sizeof(badge_buf), "%d/%d", fi + 1, count);
        lv_label_set_text(ui->featured_badge, badge_buf);
        lv_obj_set_style_text_color(ui->featured_badge,
                                    lv_color_hex(0x888888), 0);
    }

    /* Remove old compact rows */
    for (int i = 0; i < ui->compact_count; i++) {
        if (ui->compact_rows[i]) {
            lv_obj_delete(ui->compact_rows[i]);
            ui->compact_rows[i] = NULL;
        }
    }
    ui->compact_count = 0;

    /* Build compact list (all except featured, capped to visible area) */
    int y_pos = COUNTER_H + FEATURED_H + 6;
    int max_compact_rows = (SCREEN_H - y_pos) / COMPACT_ROW_H;

    for (int i = 0; i < count; i++) {
        if (i == fi) continue;
        if (ui->compact_count >= max_compact_rows) break;
        if (ui->compact_count >= NOTIF_MAX_COUNT) break;

        int ci = ui->compact_count;
        lv_obj_t *row = lv_obj_create(ui->container);
        lv_obj_remove_style_all(row);
        lv_obj_set_size(row, lv_pct(95), COMPACT_ROW_H);
        lv_obj_set_pos(row, 4, y_pos);
        lv_obj_set_scrollbar_mode(row, LV_SCROLLBAR_MODE_OFF);
        lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

        /* Tinted background */
        int row_color_idx = i % NOTIF_MAX_COUNT;
        lv_obj_set_style_bg_opa(row, LV_OPA_10, 0);
        lv_obj_set_style_bg_color(row, lv_color_hex(accent_colors[row_color_idx]), 0);

        /* Colored dot */
        lv_obj_t *dot = lv_obj_create(row);
        lv_obj_remove_style_all(dot);
        lv_obj_set_size(dot, DOT_SIZE, DOT_SIZE);
        lv_obj_set_pos(dot, 2, (COMPACT_ROW_H - DOT_SIZE) / 2);
        lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
        lv_obj_set_style_bg_color(dot, lv_color_hex(accent_colors[row_color_idx]), 0);
        lv_obj_set_style_radius(dot, DOT_SIZE / 2, 0);

        /* Project name */
        lv_obj_t *label = lv_label_create(row);
        lv_obj_set_style_text_font(label, &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_color(label, lv_color_hex(0xcccccc), 0);
        lv_obj_set_pos(label, DOT_SIZE + 6, 2);
        lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
        lv_obj_set_width(label, lv_pct(85));
        lv_label_set_text(label, ui->sorted[i].project);

        ui->compact_rows[ci] = row;
        ui->compact_count++;
        y_pos += COMPACT_ROW_H;
    }
}

/* ---------- Auto-rotation timer ---------- */

static void rotation_timer_cb(lv_timer_t *timer)
{
    notification_ui_t *ui = (notification_ui_t *)lv_timer_get_user_data(timer);
    if (!ui || ui->sorted_count <= 1) return;

    /* Cycle through notifications */
    ui->featured_idx = (ui->featured_idx + 1) % ui->sorted_count;
    rebuild_display(ui);
}
