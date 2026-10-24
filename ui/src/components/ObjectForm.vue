<script setup lang="ts">
// The form of an object or an item of ours, in the Objects tab, in the box at the bottom of the tab (ComposeBar, as everywhere; its fields scroll on a short screen, the line with the counter, Cancel and Save does not): name and kind (the name of an object that is being changed stays), the symbol (a picture to change, as in the Beacon tab), the position (the row Location of the Beacon tab, components/LocationField.vue: **Choose on map**, a click on the map, or the
// coordinates typed), the comment (the characters it has left are the counter beside the buttons), the course and speed (behind a closed fold, Moving, which is open for an object that has either), and the path the object goes by (the placeholder is the beacon's). A field with something wrong
// is red and its title says what. Save is on when there is a name, a place and a symbol and nothing is wrong; the daemon checks it all again.
import { computed, useId } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import LocationField from "@/components/LocationField.vue";
import SymbolField from "@/components/SymbolField.vue";
import { t } from "@/i18n";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { leftTitle } from "@/lib/compose";
import { onEarth, parseNumber } from "@/lib/fieldcheck";
import { placeLine } from "@/lib/locator";
import { commentLimit, draftProblems, draftReady, NAME_MAX } from "@/lib/ownobjects";

const props = defineProps<{ form: OwnObjectsView; fallbackPath: string }>();
const id = useId();
const draft = props.form.draft; // (the form's own state, kept as one object for as long as the page lives)
const problems = computed(() => draftProblems(draft));
const ready = computed(() => draftReady(draft));
/** The place the draft has in words (the line under the button); null while it is no place. */
const place = computed(() => {
  const lat = parseNumber(draft.lat);
  const lon = parseNumber(draft.lon);
  return lat !== null && lon !== null && onEarth(lat, lon) ? placeLine(lat, lon) : null;
});
/** The fold Moving (course and speed) is open while the draft has either: an object being changed that moves, or a value typed. */
const moving = computed(() => draft.course.trim() !== "" || draft.speed.trim() !== "");
const left = computed(() => commentLimit(draft) - draft.comment.trim().length);
</script>

<template>
  <ComposeBar
    class="objform"
    :label="form.editing === null ? t('objects.form.new') : t('objects.edit_label', { name: form.editing })"
    :left="left"
    :left-title="leftTitle(left, 'comment')"
    scrolls
    @submit="form.save()"
  >
    <div class="field" :class="{ invalid: problems.name }" :title="problems.name">
      <label :for="`${id}-name`">{{ t("objects.field.name") }}</label>
      <div class="field-control">
        <input
          :id="`${id}-name`"
          v-model="draft.name"
          class="input mono"
          type="text"
          :maxlength="NAME_MAX"
          :readonly="form.editing !== null"
          autocomplete="off"
          spellcheck="false"
        />
        <select v-model="draft.kind" class="input kind" :aria-label="t('objects.field.kind')" :title="t('objects.field.kind_title')">
          <option value="object">{{ t("objects.field.object") }}</option>
          <option value="item">{{ t("objects.field.item") }}</option>
        </select>
      </div>
    </div>
    <SymbolField :id="`${id}-symbol`" v-model:symbol="draft.symbol" />
    <LocationField :place="place" :picking="form.placing" :open="place === null || !!problems.lat || !!problems.lon" @pick="form.togglePlacing()">
      <div class="field" :class="{ invalid: problems.lat }" :title="problems.lat">
        <label :for="`${id}-lat`">{{ t("objects.field.lat") }}</label>
        <div class="field-control">
          <input :id="`${id}-lat`" v-model="draft.lat" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
        </div>
      </div>
      <div class="field" :class="{ invalid: problems.lon }" :title="problems.lon">
        <label :for="`${id}-lon`">{{ t("objects.field.lon") }}</label>
        <div class="field-control">
          <input :id="`${id}-lon`" v-model="draft.lon" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
        </div>
      </div>
    </LocationField>
    <div class="field" :class="{ invalid: problems.comment }" :title="problems.comment">
      <label :for="`${id}-comment`">{{ t("objects.field.comment") }}</label>
      <div class="field-control">
        <input :id="`${id}-comment`" v-model="draft.comment" class="input" type="text" autocomplete="off" />
      </div>
    </div>
    <DisclosureBox :title="t('objects.field.moving')" :open="moving">
      <div class="field" :class="{ invalid: problems.course }" :title="problems.course">
        <label :for="`${id}-course`">{{ t("objects.field.course") }}</label>
        <div class="field-control">
          <input :id="`${id}-course`" v-model="draft.course" class="input mono" type="text" inputmode="numeric" autocomplete="off" />
          <span class="unit muted">{{ t("objects.unit.deg") }}</span>
        </div>
      </div>
      <div class="field" :class="{ invalid: problems.speed }" :title="problems.speed">
        <label :for="`${id}-speed`">{{ t("objects.field.speed") }}</label>
        <div class="field-control">
          <input :id="`${id}-speed`" v-model="draft.speed" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
          <span class="unit muted">km/h</span>
        </div>
      </div>
    </DisclosureBox>
    <div class="field" :class="{ invalid: problems.path }" :title="problems.path">
      <label :for="`${id}-path`">{{ t("objects.field.path") }}</label>
      <div class="field-control">
        <input
          :id="`${id}-path`"
          v-model="draft.path"
          class="input mono"
          type="text"
          :placeholder="fallbackPath || t('route.default')"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>
    <template #buttons>
      <button type="button" class="btn" @click="form.cancel()">{{ t("objects.form.cancel") }}</button>
      <button type="submit" class="btn primary" :disabled="!ready">{{ t("objects.form.save") }}</button>
    </template>
  </ComposeBar>
</template>
