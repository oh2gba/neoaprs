<script setup lang="ts">
// The form of an object or an item of ours, in the Objects tab, in the box at the bottom of the tab (ComposeBar, as everywhere; its fields scroll on a short screen, the line with Pick on the map, the counter, Cancel and Save does not): name and kind (the name of an object that is being changed stays), the symbol (a picture to change, as in the Beacon tab), the position (typed, or
// picked with a click on the map: Pick on the map), the comment (the characters it has left are the counter beside the buttons), the course and speed, and the path the object goes by (the placeholder is the beacon's). A field with something wrong
// is red and its title says what. Save is on when there is a name, a place and a symbol and nothing is wrong; the daemon checks it all again.
import { computed, useId } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import SymbolField from "@/components/SymbolField.vue";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { leftTitle } from "@/lib/compose";
import { commentLimit, draftProblems, draftReady, NAME_MAX } from "@/lib/ownobjects";

const props = defineProps<{ form: OwnObjectsView; fallbackPath: string }>();
const id = useId();
const draft = props.form.draft; // (the form's own state, kept as one object for as long as the page lives)
const problems = computed(() => draftProblems(draft));
const ready = computed(() => draftReady(draft));
const left = computed(() => commentLimit(draft) - draft.comment.trim().length);
</script>

<template>
  <ComposeBar
    class="objform"
    :label="form.editing === null ? 'New object' : `Edit ${form.editing}`"
    :left="left"
    :left-title="leftTitle(left, 'characters', undefined, ' in the comment')"
    scrolls
    @submit="form.save()"
  >
    <div class="field" :class="{ invalid: problems.name }" :title="problems.name">
      <label :for="`${id}-name`">Name</label>
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
        <select v-model="draft.kind" class="input" aria-label="Kind">
          <option value="object">Object</option>
          <option value="item">Item</option>
        </select>
      </div>
    </div>
    <SymbolField :id="`${id}-symbol`" v-model:symbol="draft.symbol" />
    <div class="field" :class="{ invalid: problems.lat }" :title="problems.lat">
      <label :for="`${id}-lat`">Latitude</label>
      <div class="field-control">
        <input :id="`${id}-lat`" v-model="draft.lat" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
      </div>
    </div>
    <div class="field" :class="{ invalid: problems.lon }" :title="problems.lon">
      <label :for="`${id}-lon`">Longitude</label>
      <div class="field-control">
        <input :id="`${id}-lon`" v-model="draft.lon" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
      </div>
    </div>
    <div class="field" :class="{ invalid: problems.comment }" :title="problems.comment">
      <label :for="`${id}-comment`">Comment</label>
      <div class="field-control">
        <input :id="`${id}-comment`" v-model="draft.comment" class="input" type="text" autocomplete="off" />
      </div>
    </div>
    <div class="field" :class="{ invalid: problems.course }" :title="problems.course">
      <label :for="`${id}-course`">Course</label>
      <div class="field-control">
        <input :id="`${id}-course`" v-model="draft.course" class="input mono" type="text" inputmode="numeric" autocomplete="off" />
        <span class="unit muted">deg</span>
      </div>
    </div>
    <div class="field" :class="{ invalid: problems.speed }" :title="problems.speed">
      <label :for="`${id}-speed`">Speed</label>
      <div class="field-control">
        <input :id="`${id}-speed`" v-model="draft.speed" class="input mono" type="text" inputmode="decimal" autocomplete="off" />
        <span class="unit muted">km/h</span>
      </div>
    </div>
    <div class="field" :class="{ invalid: problems.path }" :title="problems.path">
      <label :for="`${id}-path`">Path</label>
      <div class="field-control">
        <input
          :id="`${id}-path`"
          v-model="draft.path"
          class="input mono"
          type="text"
          :placeholder="fallbackPath || '(default)'"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>
    <template #aside>
      <button type="button" class="btn" :class="{ primary: form.placing }" :aria-pressed="form.placing" @click="form.togglePlacing()">Pick on the map</button>
    </template>
    <template #buttons>
      <button type="button" class="btn" @click="form.cancel()">Cancel</button>
      <button type="submit" class="btn primary" :disabled="!ready">Save</button>
    </template>
  </ComposeBar>
</template>
