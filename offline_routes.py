import json, copy, os
from contextlib import nullcontext
from urllib.parse import urlparse, parse_qs
from pcmcse import cases,config,db,engine,physexam,learning,evidence,teaching
_LOCK=nullcontext()
class Handler:
    def __init__(self,path,body):
        self.path=path; self.body=body; self.headers={'Host':'localhost'}; self.result=None
    def _body(self):return self.body
    def _json(self,obj,status=200):self.result={'status':status,'body':obj};return self.result
    def _static(self,path):return self._json({'error':'Unknown local route'},404)
    def do_GET(self):
        if urlparse('http://' + self.headers.get('Host', '')).hostname not in ('127.0.0.1', 'localhost', '::1'):
            return self._json({'error': 'Use the local simulator address.'}, 403)
        url = urlparse(self.path)
        p = url.path
        if not p.startswith('/api/'):
            return self._static(p)
        if p.startswith('/api/teaching'):
            with _LOCK:
                pending = teaching.blockers()
                if p == '/api/teaching/status':
                    return self._json({'requires_assistance': bool(pending), 'attempts': pending})
                if pending:
                    return self._json({'error': 'Written solutions change active independent or exam rehearsal attempts to assisted practice before answers are shown. Deadlines and work are preserved.', 'requires_assistance': True, 'attempts': pending}, 409)
                if p == '/api/teaching':
                    return self._json({'cases': teaching.index(), 'progress': teaching.progress()})
                try:
                    cid = p.split('/')[3]
                    lesson = teaching.read(cid, parse_qs(url.query).get('variant', ['base'])[0])
                    return self._json({'lesson': lesson}) if lesson else self._json({'error': 'Unknown variation'}, 404)
                except (ValueError, IndexError, FileNotFoundError):
                    return self._json({'error': 'Walkthrough unavailable'}, 404)
        if p == '/api/bootstrap':
            settings = config.load_settings()
            return self._json({'progress': learning.progress(), 'presets': config.PRESETS, 'settings': settings, 'cases': cases.index(reveal_titles=True), 'systems': cases.systems(), 'assumptions': config.assumption_manifest(settings), 'exam_catalog': physexam.catalog_for_ui(), 'sessions': db.list_sessions(), 'vindicate': {k: v['name'] for (k, v) in config.VINDICATE.items()}, 'motherr': {k: v['name'] for (k, v) in config.MOTHERR.items()}, 'provenance': config.MNEMONIC_PROVENANCE})
        if p.startswith('/api/session/'):
            parts = p.split('/')
            sid = parts[3]
            with _LOCK:
                s = engine.load(sid)
            if not s:
                return self._json({'error': 'no such session'}, 404)
            tail = parts[4] if len(parts) > 4 else ''
            if tail == 'learning':
                # ?gap=<note row id> asks the coach for a move that fills that
                # row. It narrows the moves it was already choosing between; it
                # never widens what a coached student may see.
                return self._json(learning.state(s, gap=(parse_qs(url.query).get('gap') or [None])[0]))
            if tail == 'repair':
                try:
                    return self._json(learning.public_repair(s))
                except PermissionError as exc:
                    return self._json({'error': str(exc)}, 403)
            if tail == '':
                return self._json(engine.state_payload(s))
            if tail == 'results':
                if s.row['phase'] != 'submitted':
                    return self._json({'error': 'not submitted'}, 409)
                with _LOCK:
                    if s.row['results_json']:
                        results = json.loads(s.row['results_json'])
                    else:
                        results = s.compute_results()
                        db.update_session(sid, results_json=json.dumps(results))
                return self._json({'reader_versions': s.versions(), 'learning': learning.summary(s), 'results': results, 'case_reveal': _case_reveal(s.case), 'transcript': s.ledger.transcript(), 'evidence_summary': s.ledger.summary_counts(), 'revisions': db.list_revisions(sid)})
            if tail == 'transcript':
                if s.row['phase'] != 'submitted' and (not s.row['assisted']):
                    return self._json({'error': 'hidden until submission'}, 403)
                return self._json({'transcript': s.ledger.transcript()})
        return self._json({'error': 'not found'}, 404)
    def do_POST(self):
        if urlparse('http://' + self.headers.get('Host', '')).hostname not in ('127.0.0.1', 'localhost', '::1'):
            return self._json({'error': 'Use the local simulator address.'}, 403)
        url = urlparse(self.path)
        p = url.path
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')):
            return self._json({'error': 'Cross-origin actions are not accepted.'}, 403)
        if int(self.headers.get('Content-Length') or 0) > 1500000:
            return self._json({'error': 'Request too large.'}, 413)
        body = self._body()

        if p == '/api/progress/reset-preview':
            if (not isinstance(body, dict) or set(body) - {'scope', 'case_id'}
                    or (body.get('scope') == 'all' and 'case_id' in body)):
                return self._json({'error': 'Invalid progress-reset preview request.'}, 400)
            with _LOCK:
                try:
                    return self._json(db.preview_progress_reset(body.get('scope'), body.get('case_id')))
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 400)
                except db.sqlite3.Error:
                    return self._json({'error': 'Progress could not be read. Please try again.'}, 503)

        if p == '/api/progress/reset':
            if not isinstance(body, dict) or set(body) - {'scope', 'case_id', 'confirm', 'include_in_progress'}:
                return self._json({'error': 'Invalid progress-reset request.'}, 400)
            if body.get('scope') == 'all' and 'case_id' in body:
                return self._json({'error': 'An all-progress reset must not include a case ID.'}, 400)
            with _LOCK:
                try:
                    reset = db.reset_progress(body.get('scope'), body.get('case_id'),
                                              confirmed=body.get('confirm'),
                                              include_in_progress=body.get('include_in_progress', False))
                except db.ProgressResetConflict as exc:
                    return self._json({'error': str(exc), 'active_attempts': exc.active_attempts,
                                       'reset': False}, 409)
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 400)
                except db.sqlite3.Error:
                    return self._json({'error': 'Progress could not be reset. The reset transaction was rolled back; please try again.'}, 503)
                return self._json({'ok': True, **reset, 'progress': learning.progress(),
                                   'sessions': db.list_sessions()})
        if p == '/api/teaching/access':
            with _LOCK:
                if body.get('confirm') is not True:
                    return self._json({'error': 'Explicit assistance confirmation required'}, 400)
                try:
                    return self._json({'converted': teaching.allow_solutions(body.get('attempt_ids', []))})
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 409)
        if p == '/api/teaching/progress':
            with _LOCK:
                if teaching.blockers():
                    return self._json({'error': 'Open the teaching library through the assistance confirmation first.'}, 409)
                try:
                    return self._json(teaching.save_progress(body.get('case_id'), body.get('variant_id', 'base'), body.get('answers')))
                except (ValueError, TypeError, FileNotFoundError) as exc:
                    return self._json({'error': str(exc)}, 400)
        if p == '/api/settings':
            settings = config.load_settings()
            scoring = settings['scoring']
            scoring.update(body.pop('scoring', {}) or {})
            settings.update(body)
            settings['scoring'] = scoring
            config.save_settings(settings)
            return self._json({'settings': settings, 'assumptions': config.assumption_manifest(settings)})
        if p == '/api/session':
            case_id = body.get('case_id')
            if body.get('random'):
                import random
                pool = [c['id'] for c in cases.index() if not body.get('system') or c['system'] == body.get('system')]
                case_id = random.choice(pool) if pool else None
            if not cases.get(case_id):
                return self._json({'error': 'unknown case'}, 400)
            settings = config.load_settings()
            preset = body.get('preset') or settings.get('preset', config.DEFAULT_PRESET)
            if preset not in config.PRESETS:
                preset = config.DEFAULT_PRESET
            mode = body.get('learning_mode', 'independent')
            mode = {'practice': 'guided', 'drill': 'coached'}.get(mode, mode)
            if mode not in learning.MODES:
                return self._json({'error': 'Unknown learning mode'}, 400)
            preset = config.preset_for_learning_mode(mode, preset)
            settings.update(preset=preset, learning_mode=mode, simulation_runtime='interactive')
            visual_demo = body.get('visual_demo')
            if visual_demo:
                return self._json({'error': 'The development trial selector is retired. Choose an active library presentation.'}, 400)
            settings['visual_demo'] = visual_demo or None
            settings['scoring'] = dict(settings.get('scoring', {}), realtime_exam_durations=True, exam_time_scale=0.15 if mode == 'guided' else 1.0)
            try:
                import random
                variant_id = body.get('variant_id')
                if variant_id == 'random':
                    variant_id = random.choice(['base'] + [v['id'] for v in cases.get(case_id).get('variants', [])])
                resolved_case = cases.resolve(case_id, variant_id)
            except ValueError as exc:
                return self._json({'error': str(exc)}, 400)
            sid = db.create_session(case_id, preset, body.get('interaction_mode', 'type'), mode == 'guided' or body.get('from_walkthrough') is True, settings, case=resolved_case)
            s = engine.load(sid)
            return self._json(engine.state_payload(s))
        if not p.startswith('/api/session/'):
            return self._json({'error': 'not found'}, 404)
        parts = p.split('/')
        sid = parts[3]
        action = parts[4] if len(parts) > 4 else ''
        with _LOCK:
            s = engine.load(sid)
            if not s:
                return self._json({'error': 'no such session'}, 404)
            if action == 'guide':
                from pcmcse import guide
                try:
                    return self._json(guide.navigate(s,body))
                except PermissionError as exc:
                    return self._json({'error':str(exc)},403)
                except ValueError as exc:
                    return self._json({'error':str(exc)},400)
            if action in ('hint', 'stage', 'repair'):
                try:
                    if action == 'hint':
                        return self._json(learning.hint(s, body.get("step"), body.get("level")))
                    if action == 'repair':
                        return self._json(learning.answer_repair(s, body))
                    if not learning.allowed(s):
                        raise PermissionError('Coaching is unavailable in this mode.')
                    if body.get('step') not in [x['id'] for x in learning.STEPS]:
                        raise ValueError('Unknown encounter phase')
                    learning.record(sid, 'stage', {'step': body['step'], 'after_seq': len(s.ledger.events)})
                    return self._json(learning.state(s))
                except PermissionError as exc:
                    return self._json({'error': str(exc)}, 403)
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 400)
            if action == 'room-lesson':
                if not learning.allowed(s):
                    return self._json({'error': 'Coaching is unavailable in this mode.'}, 403)
                payload = {k: body.get(k) for k in ('lessonId', 'step', 'choice', 'correct', 'event')}
                # The guide emits start/step/skip/complete. Rejecting the two
                # navigation events made every Next and Skip return 400, which
                # the client surfaced as an error toast on a working control.
                if payload['event'] not in ('start', 'step', 'skip', 'answer', 'complete') \
                        or len(json.dumps(payload)) > 2000:
                    return self._json({'error': 'Invalid lesson action'}, 400)
                payload['unscored_ui_action'] = True
                learning.record(sid, 'room_lesson', payload)
                # Reading the taught sequence IS instructional assistance, so it
                # is recorded -- but only when the content is actually opened,
                # not again on every Next inside something already open.
                if payload['event'] == 'start' and not s.row['assisted']:
                    s.set(assisted=1)
                    s.save()
                return self._json({'ok': True})
            if action == 'transfer':
                try:
                    return self._json(learning.answer_transfer(s, body))
                except PermissionError as exc:
                    return self._json({'error': str(exc)}, 403)
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 400)
            if action in ('unity', 'room'):
                request_id = body.get('requestId', '')
                if body.get('sessionId') != sid or not isinstance(request_id, str) or (not 1 <= len(request_id) <= 128):
                    return self._json({'error': 'Mismatched session or invalid request identifier'}, 400)
                with db.connect() as conn:
                    prior = conn.execute('SELECT response_json FROM bridge_requests WHERE session_id=? AND request_id=?', (sid, request_id)).fetchone()
                recorded = any((e['meta'].get('request_id') == request_id for e in s.ledger.events))
                if prior or recorded:
                    return self._json({'ok': True, 'duplicate': True, 'events': [], 'state': engine.state_payload(s)})
                if s.row['phase'] != 'encounter':
                    return self._json({'error': 'Encounter actions are locked in this phase.'}, 409)
                kind = body.get('action')
                s.bridge_context = {'request_id': request_id, 'after_seq': len(s.ledger.events), 'renderer': 'babylon' if body.get('renderer') == 'babylon' else 'unity'}
                events = []
                if kind == 'exam':
                    mid = body.get('maneuver_id')
                    if mid not in physexam.CATALOG_BY_ID:
                        return self._json({'error': 'Unknown examination'}, 400)
                    result = s.perform_maneuver(mid, body.get('components') or [], 'Patient room examination: ' + physexam.CATALOG_BY_ID[mid]['label'])
                    if result['kind'] in ('exam_busy', 'closed', 'no_result'):
                        return self._json({'error': result['text']}, 409)
                    events = [result]
                elif kind == 'position':
                    position = body.get('position')
                    if not isinstance(position, str) or position not in engine.PATIENT_POSITIONS:
                        return self._json({'error': 'Unknown position'}, 400)
                    if s.row.get('pending_exam_json'):
                        return self._json({'error': 'Wait for the examination to finish before repositioning.'}, 409)
                    events = s.position_patient(position)
                elif kind == 'courtesy':
                    text = body.get('text', '')
                    if not isinstance(text, str) or len(text) > 500:
                        return self._json({'error': 'Invalid courtesy action'}, 400)
                    events = s.student_turn(text).get('events', [])
                elif kind == 'select_region':
                    s.ledger.add(evidence.SYSTEM, 'Selected body region: ' + str(body.get('region', ''))[:80], t_ms=s.elapsed_ms(), meta={'event': 'region_selected', 'no_finding': True})
                    s.save()
                else:
                    return self._json({'error': 'Unknown Unity action'}, 400)
                result = {'ok': True, 'events': events, 'state': engine.state_payload(engine.load(sid))}
                with db.connect() as conn:
                    conn.execute('INSERT OR IGNORE INTO bridge_requests VALUES(?,?,?)', (sid, request_id, json.dumps(result)))
                return self._json(result)
            if action == 'start':
                s.start_encounter()
                return self._json(engine.state_payload(s))
            if action == 'say':
                result = s.student_turn(body.get('text', ''), body.get('mode', 'type'), body.get('confidence'), body.get('uncertain_spans'))
                s2 = engine.load(sid)
                result['state'] = engine.state_payload(s2)
                return self._json(result)
            if action == 'exam':
                if s.row['phase'] != 'encounter':
                    return self._json({'error': 'closed'}, 409)
                res = s.perform_maneuver(body.get('maneuver_id'), body.get('components') or [], body.get('source_text', ''))
                s2 = engine.load(sid)
                return self._json({'events': [res], 'state': engine.state_payload(s2)})
            if action == 'propose_refusal':
                if s.row['phase'] != 'encounter':
                    return self._json({'error': 'closed'}, 409)
                key = body.get('key')
                spec = physexam.REFUSABLE.get(key)
                if not spec:
                    return self._json({'error': 'unknown'}, 400)
                res = s._do_exam({'status': 'refusable', 'refusable': key, 'proposed_properly': True}, 'At this point, I would do a %s.' % spec['label'].lower(), s.elapsed_ms())
                s2 = engine.load(sid)
                return self._json({'events': [res], 'state': engine.state_payload(s2)})
            if action == 'end_encounter':
                s.end_encounter_now()
                return self._json(engine.state_payload(s))
            if action == 'skip_organize':
                s.skip_organize()
                return self._json(engine.state_payload(s))
            if action == 'note':
                saved = s.save_note(body.get('note') or {})
                return self._json({'saved': bool(saved), 'phase': s.row['phase'], 'reason': '' if saved else 'The note period is closed; this save was not applied and the submitted note is unchanged.'})
            if action == 'scratch':
                saved = s.save_scratch(body.get('scratch', ''))
                return self._json({'saved': bool(saved)})
            if action == 'submit':
                s.save_note(body.get('note') or {})
                s.submit('submitted')
                return self._json(engine.state_payload(s))
            if action == 'retry':
                if s.row['phase'] != 'submitted':
                    return self._json({'error': 'not submitted'}, 409)
                try:
                    branch = engine.branch_from(sid, int(body.get('from_seq') or 0), body.get('label') or '')
                except ValueError as exc:
                    return self._json({'error': str(exc)}, 400)
                return self._json({'branch': engine.state_payload(branch), 'parent_session_id': sid})
            if action == 'interruption':
                s.record_interruption(body.get('kind', 'unknown'), body.get('detail', ''), body.get('ms', 0))
                return self._json({'recorded': True, 'integrity': s.integrity_report()})
            if action == 'revise':
                if s.row['phase'] != 'submitted':
                    return self._json({'error': 'not submitted'}, 409)
                payload = body.get('note') or {}
                results = s.compute_results(payload, label='revision (untimed)')
                rid = db.add_revision(sid, 'revision', payload, results)
                return self._json({'revision_id': rid, 'results': results})
            if action == 'delete':
                db.delete_session(sid)
                return self._json({'deleted': True})
        return self._json({'error': 'not found'}, 404)

def _case_reveal(case):
    return {'title': case['title'], 'system': case['system'], 'blurb': case.get('blurb', ''), 'curriculum_note': case.get('curriculum_note', ''), 'patient': {k: case['patient'][k] for k in ('name', 'age', 'sex', 'persona', 'affect') if k in case['patient']}, 'differentials': case.get('differentials', []), 'osteopathic': case.get('osteopathic', {}), 'area_of_concern': case.get('area_of_concern', {})}

def request(path,method,body_json):
    h=Handler(path,json.loads(body_json or '{}'))
    try:
        h.do_POST() if method=='POST' else h.do_GET()
        return json.dumps(h.result or {'status':404,'body':{'error':'Unknown local route'}})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return json.dumps({'status':500,'body':{'error':'Local engine: '+str(exc)}})
