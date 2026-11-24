// The grading page's view model: a quilt's grade, the tools to change it, section by section, and the commands that
// change it. Each change goes to the server at once, which draws it on the Looking Glass and keeps it; while one is on
// its way, only the newest waits, so the Looking Glass follows a slider as fast as it can.
import { useEffect, useState } from 'react';
import { selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import type { Grade, GradeParameter } from '../services/HoloPiApi';
import { useServices } from '../services/ServicesContext';
import { groupBySection } from '../utils/gradeUtils';
import { makeLatest } from '../utils/latestUtils';

export function useGrade(id: string) {
  const { state } = useHoloPiStore();
  const { api } = useServices();
  const [parameters, setParameters] = useState<GradeParameter[] | null>(null);
  const [grade, setGrade] = useState<Grade | null>(null); // null until the server answers.
  const [error, setError] = useState<string | null>(null);
  const [send] = useState(() => makeLatest<Grade>(async value => {
    const result = await api.setGrade(id, value);
    setError(result.ok ? null : result.error);
  }));

  // The tools and the grade, from the server, when the page opens.
  useEffect(() => {
    const controller = new AbortController();
    async function read() {
      const [list, kept] = await Promise.all([api.listGradeParameters(controller.signal),
                                              api.getGrade(id, controller.signal)]);
      if (controller.signal.aborted) return;
      if (list.ok) setParameters(list.value);
      if (kept.ok) setGrade(kept.value);
      if (!list.ok) setError(list.error);
      else if (!kept.ok) setError(kept.error);
    }
    void read();
    return () => controller.abort();
  }, [api, id]);

  function apply(next: Grade) {
    setGrade(next);
    send(next);
  }

  const ready = parameters !== null && grade !== null;
  const changed = ready && parameters.some(p => (grade.values[p.id] ?? p.default) !== p.default);
  const name = state.media?.find(medium => medium.id === id)?.name
    ?? (state.display?.media?.id === id ? state.display.media.name : id);

  return {
    name,
    sections: ready ? groupBySection(parameters, grade.values) : null,
    /** Whether the grade differs from the defaults, so that there is something to reset, or to compare with. */
    changed,
    /** Whether the Looking Glass shows the quilt without its grade, to compare. */
    showsOriginal: grade?.enabled === false,
    /** Whether the changes are seen: the Looking Glass may show something else meanwhile. */
    onScreen: selectShownId(state) === id,
    loading: !ready && error === null,
    error,
    /** Changes one value, and shows the grade again if the original was shown, so that the change is seen. */
    change(parameter: string, value: number) {
      if (grade) apply({ enabled: true, values: { ...grade.values, [parameter]: value } });
    },
    toggleOriginal() {
      if (grade) apply({ ...grade, enabled: !grade.enabled });
    },
    reset() {
      apply({ enabled: true, values: {} });
    },
  };
}
