export function truncatePath(path, maxDirs = 3) {
    if (!path || !path.trim()) return '';

    // Check if it is a URL
    const isUrl = path.startsWith('http://') || path.startsWith('https://');
    if (isUrl) {
        try {
            const urlObj = new URL(path);
            const pathname = urlObj.pathname;
            const parts = pathname.split('/').filter(Boolean);
            if (parts.length === 0) {
                return '.../' + urlObj.hostname;
            }
            const limit = Math.min(maxDirs, parts.length);
            const truncated = parts.slice(-limit).join('/');
            return '.../' + truncated;
        } catch (e) {
            // fallback if URL parsing fails
        }
    }

    // Check if it is root path (like "/" or "\")
    const trimmed = path.trim();
    if (trimmed === '/' || trimmed === '\\') return trimmed;

    // Detect if Windows formatting should be preferred
    const isWindows = trimmed.includes('\\') || /^[a-zA-Z]:/.test(trimmed) || trimmed.startsWith('\\\\');
    const separator = isWindows ? '\\' : '/';
    const prefix = isWindows ? '...\\' : '.../';

    // Split using both slashes
    const parts = trimmed.split(/[/\\]/).filter(Boolean);

    // If there is only 1 segment and no slashes at all
    if (parts.length === 1 && !trimmed.includes('/') && !trimmed.includes('\\')) {
        return trimmed;
    }

    // If segment length is less than or equal to maxDirs
    if (parts.length <= maxDirs) {
        return trimmed;
    }

    // Grab the last maxDirs segments and join them
    const truncated = parts.slice(-maxDirs).join(separator);
    return prefix + truncated;
}

export function formatMsForSubtitle(ms) {
    if (ms < 0) ms = 0;
    const hours = Math.floor(ms / 3600000);
    ms %= 3600000;
    const minutes = Math.floor(ms / 60000);
    ms %= 60000;
    const seconds = Math.floor(ms / 1000);
    const milliseconds = ms % 1000;
    return (
        String(hours).padStart(2, '0') + ':' +
        String(minutes).padStart(2, '0') + ':' +
        String(seconds).padStart(2, '0') + ',' +
        String(milliseconds).padStart(3, '0')
    );
}

export function computeGapLabel(prev, current) {
    if (!prev) return 'N/A';
    const gap = current.start_ms - prev.end_ms;
    return gap + 'ms';
}

export function parseSrtTextClient(srtText) {
    const segments = [];
    if (!srtText) return segments;

    const normalized = srtText.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const blocks = normalized.split(/\n\n+/);

    let indexCount = 1;
    for (const block of blocks) {
        if (!block.trim()) continue;
        const lines = block.trim().split('\n');
        if (lines.length < 2) continue;

        let timeLineIdx = 0;
        if (/^\d+$/.test(lines[0].trim())) {
            timeLineIdx = 1;
        }

        const timeLine = lines[timeLineIdx];
        if (!timeLine || !timeLine.includes('-->')) continue;

        const parts = timeLine.split('-->');
        const startStr = parts[0].trim();
        const endStr = parts[1].trim();

        const startMs = parseSrtTimestampToMs(startStr);
        const endMs = parseSrtTimestampToMs(endStr);
        const text = lines.slice(timeLineIdx + 1).join('\n').trim();

        segments.push({
            index: indexCount++,
            start_ms: startMs,
            end_ms: endMs,
            text: text
        });
    }

    return segments;
}

function parseSrtTimestampToMs(timeStr) {
    const match = timeStr.match(/(\d+):(\d+):(\d+)[,\.](\d+)/);
    if (!match) return 0;
    const hrs = parseInt(match[1], 10);
    const mins = parseInt(match[2], 10);
    const secs = parseInt(match[3], 10);
    const ms = parseInt(match[4], 10);
    return hrs * 3600000 + mins * 60000 + secs * 1000 + ms;
}

export function exportSegmentsToSrtClient(segments) {
    return segments.map(seg => {
        return `${seg.index}\n${formatMsToSrtTimestamp(seg.start_ms)} --> ${formatMsToSrtTimestamp(seg.end_ms)}\n${seg.text}`;
    }).join('\n\n') + '\n';
}

function formatMsToSrtTimestamp(ms) {
    const hrs = Math.floor(ms / 3600000);
    const mins = Math.floor((ms % 3600000) / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    const msecs = ms % 1000;

    const pad = (num, size) => ('000' + num).slice(-size);
    return `${pad(hrs, 2)}:${pad(mins, 2)}:${pad(secs, 2)},${pad(msecs, 3)}`;
}

export function replaceSegmentTextClient(segments, targetIndex, newText) {
    return segments.map(seg => {
        if (seg.index === targetIndex) {
            return { ...seg, text: newText };
        }
        return seg;
    });
}

export function mergeSegmentsClient(segments, startIndex, endIndex, allowLargeGap = false) {
    const startIdx = segments.findIndex(s => s.index === startIndex);
    const endIdx = segments.findIndex(s => s.index === endIndex);
    if (startIdx === -1 || endIdx === -1 || startIdx >= endIdx) {
        throw new Error("Chỉ số gộp không hợp lệ");
    }

    for (let i = startIdx + 1; i <= endIdx; i++) {
        if (segments[i].index !== segments[i - 1].index + 1) {
            throw new Error("Chỉ có thể gộp các dòng phụ đề liên tiếp nhau");
        }
    }

    const maxGapMs = 300;
    const maxDurationMs = 6000;
    const maxChars = 120;

    if (!allowLargeGap) {
        for (let i = startIdx + 1; i <= endIdx; i++) {
            const gap = segments[i].start_ms - segments[i - 1].end_ms;
            if (gap > maxGapMs) {
                throw new Error("gap");
            }
        }
    }

    const totalDuration = segments[endIdx].end_ms - segments[startIdx].start_ms;
    if (totalDuration > maxDurationMs) {
        throw new Error(`Tổng độ dài gộp (${totalDuration}ms) vượt quá giới hạn tối đa ${maxDurationMs}ms`);
    }

    const mergedText = segments.slice(startIdx, endIdx + 1).map(s => s.text).join(' ');
    if (mergedText.length > maxChars) {
        throw new Error(`Tổng số ký tự gộp (${mergedText.length}) vượt quá giới hạn tối đa ${maxChars} ký tự`);
    }

    const mergedSegment = {
        index: startIndex,
        start_ms: segments[startIdx].start_ms,
        end_ms: segments[endIdx].end_ms,
        text: mergedText
    };

    const newSegments = [
        ...segments.slice(0, startIdx),
        mergedSegment,
        ...segments.slice(endIdx + 1)
    ];

    return newSegments.map((s, idx) => ({ ...s, index: idx + 1 }));
}

export function splitSegmentClient(segments, targetIndex, splitAtMs, firstText, secondText) {
    const idx = segments.findIndex(s => s.index === targetIndex);
    if (idx === -1) {
        throw new Error("Dòng phụ đề cần tách không tồn tại");
    }

    const seg = segments[idx];
    if (splitAtMs <= seg.start_ms || splitAtMs >= seg.end_ms) {
        throw new Error("Thời điểm tách phải nằm giữa thời điểm bắt đầu và kết thúc");
    }

    const firstSeg = {
        index: seg.index,
        start_ms: seg.start_ms,
        end_ms: splitAtMs,
        text: firstText
    };

    const secondSeg = {
        index: seg.index + 1,
        start_ms: splitAtMs,
        end_ms: seg.end_ms,
        text: secondText
    };

    const newSegments = [
        ...segments.slice(0, idx),
        firstSeg,
        secondSeg,
        ...segments.slice(idx + 1)
    ];

    return newSegments.map((s, i) => ({ ...s, index: i + 1 }));
}
