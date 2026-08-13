import { state } from './state.js';
import { initSubtitleSources, onSrtLoaded, onBatchCreated } from './subtitle_sources.js';
import { initSubtitleQueue, renderQueueTable, startQueuePolling, onOpenJob } from './subtitle_queue.js';
import { initSubtitleModal, openModalForJob, openModalForSrt } from './subtitle_modal.js';

export function initSubtitle() {
    initSubtitleSources();
    initSubtitleQueue();
    initSubtitleModal();

    onSrtLoaded(async (content, path) => {
        await openModalForSrt(content, path);
    });

    onBatchCreated((batchId, snapshot) => {
        renderQueueTable(snapshot);
        startQueuePolling(batchId);
    });

    onOpenJob((job) => {
        openModalForJob(job, state.currentSubtitleBatchId, (updatedSnapshot) => {
            renderQueueTable(updatedSnapshot);
        });
    });
}
