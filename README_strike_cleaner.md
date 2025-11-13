# Strike LLM Cleaner Requirements

## Dependencies

Install the required Python packages:

```bash
pip install openai
```

## Environment Variables

Set your OpenAI API key:

```bash
set OPENAI_API_KEY=your_api_key_here
```

## Usage

```bash
python strike_llm_cleaner.py <input_folder> <output_folder>
```

Where:
- `<input_folder>` contains JSON files from `raw_strike_description_collector.py`
- `<output_folder>` will contain the processed JSON files with structured strike data

## Configuration

You can modify the OpenAI model at the top of `strike_llm_cleaner.py`:

```python
OPENAI_MODEL = "gpt-4o"  # Change to "gpt-3.5-turbo" or other models
```