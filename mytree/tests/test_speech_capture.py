"""PCM capture failure classification and official ASR response recovery."""
import base64,io,json,math,struct,sys,unittest,wave
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ai,speech

def wav(duration=1,amplitude=4000,rate=16000,width=2):
    out=io.BytesIO()
    with wave.open(out,'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(width);stream.setframerate(rate)
        if width==2:stream.writeframes(b''.join(struct.pack('<h',int(amplitude*math.sin(i*.1))) for i in range(int(duration*rate))))
        else:stream.writeframes(bytes([128])*int(duration*rate))
    return out.getvalue()

class CaptureTests(unittest.TestCase):
    def test_silent_recording_is_rejected_before_provider_call(self):
        for raw in (wav(amplitude=0),wav(width=1)):
            with patch.object(speech,'_request') as upstream:
                with self.assertRaises(ai.ModelError) as raised:speech.handle({'action':'transcribe','audio_data':'data:audio/wav;base64,'+base64.b64encode(raw).decode()})
                self.assertEqual(raised.exception.code,'SPEECH_NO_AUDIO');self.assertIn('静音',str(raised.exception));upstream.assert_not_called()
    def test_short_long_and_truncated_recordings_have_specific_guidance(self):
        for raw,hint in ((wav(.1),'录音太短'),(wav(21.1),'20秒'),(wav()[:-20],'没有保存完整')):
            with self.assertRaises(ValueError) as raised:speech.validate_wav(raw)
            self.assertIn(hint,str(raised.exception))
    def test_streaming_tts_wav_size_placeholders_use_actual_complete_frames(self):
        for marker in (0x7fffff9b,0xffffffff):
            raw=bytearray(wav());raw[4:8]=(marker+36 if marker<0xffffffdb else marker).to_bytes(4,'little');raw[40:44]=marker.to_bytes(4,'little')
            speech.validate_wav(bytes(raw))
            with self.assertRaises(ValueError):speech.validate_wav(bytes(raw[:-1]))
        raw=bytearray(wav(.1));raw[4:8]=(0x7fffffbf).to_bytes(4,'little');raw[40:44]=(0x7fffff9b).to_bytes(4,'little')
        with self.assertRaises(ValueError) as raised:speech.validate_wav(bytes(raw))
        self.assertIn('录音太短',str(raised.exception))
        raw=bytearray(wav(21.1));raw[4:8]=(0x7fffffbf).to_bytes(4,'little');raw[40:44]=(0x7fffff9b).to_bytes(4,'little')
        with self.assertRaises(ValueError) as raised:speech.validate_wav(bytes(raw))
        self.assertIn('20秒',str(raised.exception))
        raw=bytearray(wav());raw[4:8]=(0x7fff1111).to_bytes(4,'little');raw[40:44]=(0x7fff0001).to_bytes(4,'little')
        with self.assertRaises(ValueError):speech.validate_wav(bytes(raw))
    def test_quiet_non_silent_pcm_is_not_mistaken_for_silence(self):
        speech.validate_wav(wav(amplitude=40));speech.validate_wav(wav(rate=48000))
    def test_empty_asr_text_is_distinct_from_bad_response_format(self):
        for qwen in (True,False):
            empty={'choices':[{'message':{'content':'  '}}]} if qwen else {'text':''}
            with self.assertRaises(ai.ModelError) as raised:speech.transcription_text(json.dumps(empty),qwen)
            self.assertEqual(raised.exception.code,'SPEECH_NOT_HEARD');self.assertIn('靠近麦克风',str(raised.exception))
            with self.assertRaises(ai.ModelError) as raised:speech.transcription_text('{"error":"PRIVATE_KEY"}',qwen)
            self.assertEqual(raised.exception.code,'SPEECH_RESPONSE_INVALID');self.assertNotIn('PRIVATE_KEY',str(raised.exception))
    def test_official_text_response_is_trimmed_and_bounded(self):
        self.assertEqual(speech.transcription_text('{"choices":[{"message":{"content":" Hello tree. "}}]}',True),'Hello tree.')
        with self.assertRaises(ai.ModelError) as raised:speech.transcription_text(json.dumps({'text':'x'*801}))
        self.assertEqual(raised.exception.code,'SPEECH_TEXT_TOO_LONG')
    def test_valid_recording_reaches_official_asr_and_recovers_after_empty_reply(self):
        cfg=ai.Settings(asr_protocol='qwen',key='TEST',asr='qwen3-asr-flash')
        body={'action':'transcribe','audio_data':'data:audio/wav;base64,'+base64.b64encode(wav()).decode()}
        with patch.object(ai,'settings',return_value=cfg),patch.object(speech,'_request') as upstream:
            upstream.return_value=(b'{"choices":[{"message":{"content":""}}]}','application/json')
            with self.assertRaises(ai.ModelError):speech.handle(body)
            upstream.return_value=(b'{"choices":[{"message":{"content":"Hello tree."}}]}','application/json')
            self.assertEqual(speech.handle(body)['text'],'Hello tree.')
            self.assertEqual(upstream.call_count,2)

if __name__=='__main__':unittest.main(verbosity=2)
