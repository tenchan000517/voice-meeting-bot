import ollama
import os
import aiofiles
from datetime import datetime
from typing import List, Dict, Optional
import logging
import asyncio
import json
import httpx

logger = logging.getLogger(__name__)

class SummarizationService:
    """Service for meeting summarization using Ollama"""
    
    def __init__(self):
        self.client = None
        self.host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.model = os.getenv('OLLAMA_MODEL', 'gemma2:2b')
        self.timeout = int(os.getenv('OLLAMA_TIMEOUT', 300))
        self.output_dir = os.getenv('OUTPUT_DIR', './output')
        self._ensure_output_dir()
        
        # Summary templates
        self.templates = {
            'meeting_summary': """
以下は会議の文字起こしです。この内容を基に、日本語で分かりやすい議事録を作成してください。

【会議情報】
- 会議ID: {meeting_id}
- 参加者: {participants}
- 時間: {duration}分

【文字起こし】
{transcript}

【出力形式】
# 会議議事録

## 📋 会議概要
- **日時**: {date}
- **時間**: {duration}分
- **参加者**: {participant_count}名

## 📝 主な議題・内容
（ここに主要な話し合いの内容を3-5つのポイントで整理）

## ✅ 決定事項
（ここに会議で決まったことを箇条書きで記載）

## 📋 アクションアイテム
（ここに今後のタスクや宿題があれば記載）

## 💭 その他・メモ
（ここに補足情報や追加メモがあれば記載）
""",

            'chunk_summary': """
以下は会議の一部（{time_range}）の文字起こしです。
この部分の内容を150文字程度で要約してください。

【時間帯】{time_range}
【参加者】{participants}
【文字起こし】
{transcript}

【要約（150文字程度）】
""",

            'chunk_key_points': """
以下は会議の一部（{time_range}）の文字起こしです。
この部分の重要なポイントを2-3個、箇条書きで抽出してください。

【時間帯】{time_range}
【文字起こし】
{transcript}

【重要ポイント】
• 
• 
• 
""",
            
            'key_points': """
以下の会議文字起こしから、重要なポイントを3-5つ抽出してください：

{transcript}

出力は以下の形式で：
• ポイント1
• ポイント2
• ポイント3
""",
            
            'action_items': """
以下の会議文字起こしから、アクションアイテム（今後のタスク・宿題）を抽出してください：

{transcript}

出力は以下の形式で：
□ タスク1 - 担当者（もし明記されていれば）
□ タスク2 - 担当者（もし明記されていれば）
"""
        }
    
    def _ensure_output_dir(self):
        """Ensure output directory exists"""
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def initialize(self):
        """Initialize Ollama connection"""
        try:
            logger.info(f"Connecting to Ollama at {self.host}")
            
            # Test connection
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                if response.status_code == 200:
                    models = response.json()
                    logger.info(f"Available Ollama models: {[m['name'] for m in models.get('models', [])]}")
                    
                    # Check if our model is available
                    model_names = [m['name'] for m in models.get('models', [])]
                    if self.model not in model_names and not any(self.model in name for name in model_names):
                        logger.warning(f"Model {self.model} not found. Available models: {model_names}")
                        # Try to pull the model
                        await self._pull_model()
                    else:
                        logger.info(f"Model {self.model} is available")
                else:
                    raise Exception(f"Failed to connect to Ollama: {response.status_code}")
            
            logger.info("Ollama connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {e}")
            raise
    
    async def _pull_model(self):
        """Pull the required model if not available"""
        try:
            logger.info(f"Pulling model {self.model}...")
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.host}/api/pull",
                    json={"name": self.model}
                )
                
                if response.status_code == 200:
                    logger.info(f"Successfully pulled model {self.model}")
                else:
                    logger.error(f"Failed to pull model {self.model}: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
    
    def is_ready(self) -> bool:
        """Check if summarization service is ready"""
        try:
            # Simple sync check - in production, you might want a more robust check
            return True
        except:
            return False
    
    async def create_summary(
        self,
        meeting_id: str,
        transcript: str,
        participants: List[str],
        duration: int,
        summary_type: str = 'full'
    ) -> str:
        """Create meeting summary using Ollama"""
        try:
            logger.info(f"Creating {summary_type} summary for meeting {meeting_id}")
            
            if summary_type == 'full':
                template = self.templates['meeting_summary']
                prompt = template.format(
                    meeting_id=meeting_id,
                    participants=', '.join(participants),
                    duration=duration,
                    transcript=transcript,
                    date=datetime.now().strftime('%Y-%m-%d %H:%M'),
                    participant_count=len(participants)
                )
            elif summary_type == 'key_points':
                template = self.templates['key_points']
                prompt = template.format(transcript=transcript)
            elif summary_type == 'action_items':
                template = self.templates['action_items']
                prompt = template.format(transcript=transcript)
            else:
                raise ValueError(f"Unknown summary type: {summary_type}")
            
            # Generate summary using Ollama
            summary = await self._generate_with_ollama(prompt)
            
            logger.info(f"Summary generated successfully for meeting {meeting_id}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to create summary: {e}")
            raise
    
    async def _generate_with_ollama(self, prompt: str) -> str:
        """Generate text using Ollama API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,  # Lower temperature for more consistent output
                            "top_p": 0.9,
                            "top_k": 40
                        }
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '')
                else:
                    raise Exception(f"Ollama API error: {response.status_code} - {response.text}")
                    
        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            raise Exception("Request to Ollama timed out")
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
    
    async def create_comprehensive_summary(
        self,
        meeting_id: str,
        transcript: str,
        participants: List[str],
        duration: int
    ) -> Dict[str, str]:
        """Create comprehensive summary with multiple sections"""
        try:
            logger.info(f"Creating comprehensive summary for meeting {meeting_id}")
            
            # Generate different types of summaries concurrently
            tasks = []
            
            # Full summary
            tasks.append(
                self.create_summary(meeting_id, transcript, participants, duration, 'full')
            )
            
            # Key points
            tasks.append(
                self.create_summary(meeting_id, transcript, participants, duration, 'key_points')
            )
            
            # Action items
            tasks.append(
                self.create_summary(meeting_id, transcript, participants, duration, 'action_items')
            )
            
            # Wait for all summaries to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            summary_data = {
                'full_summary': results[0] if not isinstance(results[0], Exception) else "要約生成に失敗しました",
                'key_points': results[1] if not isinstance(results[1], Exception) else "重要ポイントの抽出に失敗しました",
                'action_items': results[2] if not isinstance(results[2], Exception) else "アクションアイテムの抽出に失敗しました",
                'meeting_id': meeting_id,
                'generated_at': datetime.now().isoformat(),
                'participants': participants,
                'duration_minutes': duration
            }
            
            logger.info(f"Comprehensive summary completed for meeting {meeting_id}")
            return summary_data
            
        except Exception as e:
            logger.error(f"Failed to create comprehensive summary: {e}")
            raise
    
    async def save_summary(self, meeting_id: str, summary_data: Dict[str, str]) -> str:
        """Save summary to markdown file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"meeting_{meeting_id}_{timestamp}.md"
            file_path = os.path.join(self.output_dir, filename)
            
            # Create markdown content
            if isinstance(summary_data, dict):
                markdown_content = self._format_comprehensive_markdown(summary_data)
            else:
                # Simple string summary
                markdown_content = f"# 会議議事録\n\n**会議ID**: {meeting_id}\n**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{summary_data}"
            
            # Save to file
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(markdown_content)
            
            logger.info(f"Summary saved to: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
            raise
    
    def _format_comprehensive_markdown(self, summary_data: Dict[str, str]) -> str:
        """Format comprehensive summary as markdown"""
        content = f"""# 🎙️ 会議議事録

**会議ID**: `{summary_data.get('meeting_id', 'N/A')}`  
**生成日時**: {summary_data.get('generated_at', datetime.now().isoformat())}  
**参加者**: {', '.join(summary_data.get('participants', []))}  
**録音時間**: {summary_data.get('duration_minutes', 0)}分

---

## 📋 詳細議事録

{summary_data.get('full_summary', '詳細議事録が生成されませんでした')}

---

## ⭐ 重要ポイント

{summary_data.get('key_points', '重要ポイントが抽出されませんでした')}

---

## ✅ アクションアイテム

{summary_data.get('action_items', 'アクションアイテムが見つかりませんでした')}

---

*この議事録は AI により自動生成されました。内容に誤りがある可能性がありますので、必要に応じて確認・修正してください。*
"""
        return content
    
    async def create_hierarchical_summary(
        self,
        meeting_id: str,
        chunk_transcripts: List[Dict[str, str]],
        participants: List[str],
        total_duration: int
    ) -> Dict[str, str]:
        """Create hierarchical summary for long meetings"""
        try:
            logger.info(f"Creating hierarchical summary for {len(chunk_transcripts)} chunks")
            
            # Phase 1: Summarize each chunk individually
            chunk_summaries = []
            for i, chunk in enumerate(chunk_transcripts):
                logger.info(f"Summarizing chunk {i+1}/{len(chunk_transcripts)}")
                
                chunk_prompt = f"""
以下は会議の一部（{i*30}分〜{(i+1)*30}分）の文字起こしです。
この部分の要点を200文字程度で要約してください。

【文字起こし】
{chunk['text']}

【要約】
"""
                chunk_summary = await self._generate_with_ollama(chunk_prompt)
                chunk_summaries.append({
                    'chunk_index': i,
                    'time_range': f"{i*30}分〜{(i+1)*30}分",
                    'summary': chunk_summary.strip()
                })
                
                # Small delay to avoid overwhelming Ollama
                await asyncio.sleep(1)
            
            # Phase 2: Create final summary from chunk summaries
            combined_summaries = "\n\n".join([
                f"【{cs['time_range']}】\n{cs['summary']}" 
                for cs in chunk_summaries
            ])
            
            final_prompt = f"""
以下は{total_duration}分間の会議の各30分ごとの要約です。
これらを統合して、会議全体の議事録を作成してください。

【会議情報】
- 会議ID: {meeting_id}
- 参加者: {', '.join(participants)}
- 総時間: {total_duration}分

【各時間帯の要約】
{combined_summaries}

【出力形式】
# 会議議事録

## 📋 会議概要
- **日時**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **時間**: {total_duration}分
- **参加者**: {len(participants)}名

## 📝 会議の流れ
（時系列での主要トピックを記載）

## ⭐ 主な議題・決定事項
（重要な決定事項を箇条書きで）

## ✅ 今後のアクション
（必要なアクションアイテムを記載）

## 📌 補足事項
（その他の重要事項があれば記載）
"""
            
            final_summary = await self._generate_with_ollama(final_prompt)
            
            # Return comprehensive result
            return {
                'full_summary': final_summary,
                'chunk_summaries': chunk_summaries,
                'meeting_id': meeting_id,
                'generated_at': datetime.now().isoformat(),
                'participants': participants,
                'duration_minutes': total_duration,
                'chunk_count': len(chunk_transcripts)
            }
            
        except Exception as e:
            logger.error(f"Failed to create hierarchical summary: {e}")
            raise
    
    async def cleanup_old_summaries(self, days: int = 30):
        """Clean up old summary files"""
        try:
            current_time = datetime.now()
            cutoff_time = current_time.timestamp() - (days * 24 * 60 * 60)
            
            for filename in os.listdir(self.output_dir):
                if filename.endswith('.md'):
                    file_path = os.path.join(self.output_dir, filename)
                    file_stat = os.stat(file_path)
                    
                    if file_stat.st_mtime < cutoff_time:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old summary: {filename}")
                        
        except Exception as e:
            logger.error(f"Summary cleanup failed: {e}")
    
    def get_available_models(self) -> List[str]:
        """Get list of available Ollama models"""
        try:
            # This would be implemented with a synchronous request
            # For now, return common models
            return [
                'gemma2:2b',
                'gemma2:9b',
                'llama3.1:8b',
                'mistral:7b',
                'codellama:7b'
            ]
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
    
    async def test_generation(self) -> bool:
        """Test if the service can generate text"""
        try:
            test_prompt = "これは接続テストです。「OK」とだけ回答してください。"
            result = await self._generate_with_ollama(test_prompt)
            logger.info(f"Test generation result: {result}")
            return len(result.strip()) > 0
        except Exception as e:
            logger.error(f"Test generation failed: {e}")
            return False
    
    async def create_realtime_chunk_summary(
        self,
        meeting_id: str,
        chunk_index: int,
        transcript_text: str,
        participants: List[str],
        chunk_start_time: datetime,
        chunk_end_time: datetime
    ) -> Dict[str, str]:
        """Create real-time summary for a single chunk"""
        try:
            logger.info(f"Creating real-time summary for chunk {chunk_index} of meeting {meeting_id}")
            
            # Calculate time range
            start_minutes = chunk_index * 30
            end_minutes = (chunk_index + 1) * 30
            time_range = f"{start_minutes}分〜{end_minutes}分"
            
            # Generate chunk summary
            summary_template = self.templates['chunk_summary']
            summary_prompt = summary_template.format(
                time_range=time_range,
                participants=', '.join(participants),
                transcript=transcript_text
            )
            
            # Generate key points
            key_points_template = self.templates['chunk_key_points']
            key_points_prompt = key_points_template.format(
                time_range=time_range,
                transcript=transcript_text
            )
            
            # Generate both in parallel
            summary_task = self._generate_with_ollama(summary_prompt)
            key_points_task = self._generate_with_ollama(key_points_prompt)
            
            summary_result, key_points_result = await asyncio.gather(
                summary_task, key_points_task, return_exceptions=True
            )
            
            # Handle results
            summary_text = summary_result if not isinstance(summary_result, Exception) else "要約生成に失敗しました"
            key_points_text = key_points_result if not isinstance(key_points_result, Exception) else "重要ポイントの抽出に失敗しました"
            
            chunk_summary_data = {
                'meeting_id': meeting_id,
                'chunk_index': chunk_index,
                'time_range': time_range,
                'chunk_start_time': chunk_start_time.isoformat(),
                'chunk_end_time': chunk_end_time.isoformat(),
                'transcript_text': transcript_text,
                'summary_text': summary_text.strip(),
                'key_points': key_points_text.strip(),
                'participants': participants,
                'generated_at': datetime.now().isoformat()
            }
            
            logger.info(f"Chunk summary created successfully for chunk {chunk_index}")
            return chunk_summary_data
            
        except Exception as e:
            logger.error(f"Failed to create chunk summary: {e}")
            raise
    
    def format_chunk_summary_for_discord(self, chunk_data: Dict[str, str]) -> str:
        """Format chunk summary for Discord posting"""
        try:
            return f"""## 📝 リアルタイム議事録（{chunk_data['time_range']}）

**会議ID**: `{chunk_data['meeting_id']}`
**時間帯**: {chunk_data['time_range']}
**参加者**: {', '.join(chunk_data.get('participants', []))}

### 📋 この時間帯の要約
{chunk_data['summary_text']}

### ⭐ 重要ポイント
{chunk_data['key_points']}

---
*この要約は{chunk_data['time_range']}の録音終了時に自動生成されました*
"""
        except Exception as e:
            logger.error(f"Failed to format chunk summary: {e}")
            return f"要約の整形に失敗しました: {str(e)}"
    
    async def create_final_integrated_summary(
        self,
        meeting_id: str,
        chunk_summaries: List[Dict],
        total_duration: int,
        all_participants: List[str]
    ) -> Dict[str, str]:
        """Create final integrated summary from all chunk summaries"""
        try:
            logger.info(f"Creating final integrated summary for meeting {meeting_id}")
            
            # Combine all chunk summaries
            combined_chunk_text = ""
            for chunk in chunk_summaries:
                time_range = chunk.get('time_range', f"チャンク{chunk.get('chunk_index', '?')}")
                summary = chunk.get('summary_text', '')
                key_points = chunk.get('key_points', '')
                
                combined_chunk_text += f"""
【{time_range}】
要約: {summary}
重要ポイント: {key_points}

"""
            
            # Create integrated summary prompt
            integrated_prompt = f"""
以下は{total_duration}分間の会議の各時間帯の要約です。
これらを統合して、会議全体の包括的な議事録を作成してください。

【会議情報】
- 会議ID: {meeting_id}
- 総時間: {total_duration}分
- 参加者: {', '.join(all_participants)}

【各時間帯の要約】
{combined_chunk_text}

【出力形式】
# 🎙️ 会議議事録（統合版）

## 📋 会議概要
- **日時**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **総時間**: {total_duration}分
- **参加者**: {len(all_participants)}名

## 📝 会議全体の流れ
（時系列での主要な話し合いの流れを記載）

## ⭐ 主要な議題・決定事項
（会議で決まった重要事項を箇条書きで）

## ✅ アクションアイテム
（今後必要なタスクや宿題を記載）

## 📌 補足事項
（その他の重要な情報があれば記載）

## 🕐 時間帯別要約
（各時間帯の詳細な内容）
"""
            
            # Generate integrated summary
            integrated_summary = await self._generate_with_ollama(integrated_prompt)
            
            # Save integrated summary
            summary_data = {
                'full_summary': integrated_summary,
                'meeting_id': meeting_id,
                'generated_at': datetime.now().isoformat(),
                'participants': all_participants,
                'duration_minutes': total_duration,
                'chunk_count': len(chunk_summaries),
                'summary_type': 'integrated'
            }
            
            logger.info(f"Final integrated summary completed for meeting {meeting_id}")
            return summary_data
            
        except Exception as e:
            logger.error(f"Failed to create integrated summary: {e}")
            raise