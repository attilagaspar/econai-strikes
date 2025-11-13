# EconAI Strikes - Historical Strike Data Extraction Pipeline

This repository contains a complete pipeline for extracting and analyzing historical strike data from Hungarian newspaper OCR results, specifically from the "TŐKE ÉS MUNKA" (Capital and Labor) column of the Népszava labor journal from the early 20th century.

## 📋 Overview

The pipeline consists of four main scripts that work together to transform raw OCR newspaper data into structured strike databases:
1. **`newspaper_layout_processor.py`** - Extracts row and column data for layoutparser output, fixes column lengths.
2. **`raw_strike_description_collector.py`** - Extracts "TŐKE ÉS MUNKA" column content from OCR results
3. **`strike_llm_cleaner.py`** - Uses OpenAI API to extract structured strike data from the text
4. **`compile_strike_csv.py`** - Compiles all strike data into a single CSV for analysis

## 🔧 Requirements

- Python 3.7+
- OpenAI API key (for `strike_llm_cleaner.py`)
- Required Python packages (see `requirements.txt`)

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/attilagaspar/econai-strikes.git
cd econai-strikes
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up your OpenAI API key:
```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# Linux/Mac
export OPENAI_API_KEY=your_api_key_here
```

## 🚀 Usage

### Step 1: Extract Column Content

Extract "TŐKE ÉS MUNKA" column content from OCR JSON files:

```bash
python raw_strike_description_collector.py <input_folder> <output_folder>
```

**Input**: Folder containing JSON files with OCR results from newspaper pages
**Output**: Individual JSON files containing extracted column content

**Features**:
- Searches for hasabkozi_cim containing 'tőke' and 'munka' (case insensitive)
- Extracts newspaper header (oldalfejlec) from the same page
- Collects content following document structure until next subtitle/header
- Natural sorting of input files for consistent processing

### Step 2: Extract Structured Strike Data

Use OpenAI API to analyze the text and extract structured strike information:

```bash
python strike_llm_cleaner.py <input_folder> <output_folder> [--force]
```

**Input**: Folder containing JSON files from Step 1
**Output**: JSON files with structured strike data

**Features**:
- Extracts publication dates from newspaper headers
- Uses different OpenAI models for date extraction and strike analysis
- Skips files with existing output (unless `--force` is used)
- Extracts 11 structured fields for each strike:
  - `event_date` - Strike date in ISO 8601 format
  - `industry_txt` - Industry description
  - `industry_SIC` - Industry SIC code
  - `participants_txt` - Participant description
  - `participants_ISCO` - Participant ISCO code
  - `firm_name` - Company or estate name
  - `location_txt` - Location as described
  - `location_official` - Current official settlement name
  - `location_geonames_id` - GeoNames ID
  - `strike_status` - Status (planned/ongoing/resolved)
  - `description_en` - 30-word English description

### Step 3: Compile to CSV

Compile all strike data into a single CSV file for analysis:

```bash
python compile_strike_csv.py <input_folder> <output_csv_file>
```

**Input**: Folder containing JSON files from Step 2
**Output**: Single CSV file with all strike records

**Features**:
- Adds publication_date as a column for each strike
- Includes source file information for traceability
- Handles missing fields gracefully
- Orders columns logically for analysis

## ⚙️ Configuration

### OpenAI Models

You can configure different models for different tasks in `strike_llm_cleaner.py`:

```python
# Configuration - Modify these as needed
OPENAI_DATE_MODEL = "gpt-4o-mini"  # Model for date extraction (simpler task)
OPENAI_STRIKES_MODEL = "gpt-5-nano"  # Model for strike analysis (complex task)
```

**Recommended configurations**:
- **Cost-optimized**: `gpt-4o-mini` for both tasks
- **Accuracy-optimized**: `gpt-5-nano` or `gpt-4o` for strike analysis
- **Balanced**: `gpt-4o-mini` for dates, `gpt-5-nano` for strikes

## 📊 Output Format

### Final CSV Structure

```csv
publication_date,source_file,newspaper_header,event_date,industry_txt,industry_SIC,participants_txt,participants_ISCO,firm_name,location_txt,location_official,location_geonames_id,strike_status,description_en
1903-01-03,toke_munka_Nepszava_1903_01__pages1-50_images_page_13.json,"NÉPSZAVA 1903. január 3.",1903-01-02,Mining,1011,Coal miners,7111,Salgótarján Coal Mine,Salgótarján,Salgótarján,715429,ongoing,Coal miners strike for better wages and working conditions
```

## 📂 File Structure

```
econai-strikes/
├── raw_strike_description_collector.py  # Step 1: Extract column content
├── strike_llm_cleaner.py               # Step 2: AI-powered data extraction
├── compile_strike_csv.py               # Step 3: Compile to CSV
├── extract_newspaper_text.py           # Helper script for text extraction
├── newspaper_layout_processor.py       # Helper script for layout processing
├── requirements.txt                    # Python dependencies
├── README.md                          # This file
└── README_strike_cleaner.md           # Detailed setup for strike cleaner
```

## 🔍 Example Workflow

1. **Prepare OCR data**: Ensure your newspaper OCR results are in JSON format with proper structure
2. **Extract columns**: Run `raw_strike_description_collector.py` to extract "TŐKE ÉS MUNKA" content
3. **Process with AI**: Run `strike_llm_cleaner.py` to extract structured strike data
4. **Compile results**: Run `compile_strike_csv.py` to create the final database
5. **Analyze**: Use the CSV file for statistical analysis, visualization, or further research

## 🐛 Troubleshooting

### Common Issues

1. **OpenAI API errors**: 
   - Ensure your API key is set correctly
   - Different models support different parameters (temperature, max_tokens vs max_completion_tokens)
   - Check your API usage limits

2. **Empty responses from OpenAI**:
   - Reasoning models like `gpt-5-nano` may need higher token limits
   - Try increasing `max_completion_tokens` in the query function

3. **Missing files**:
   - Use `--force` flag to reprocess existing files
   - Check file permissions and paths

4. **Encoding issues**:
   - All scripts use UTF-8 encoding for Hungarian text
   - Ensure your terminal supports UTF-8 output

### Debug Mode

For detailed debugging, the scripts include verbose logging:
- Date extraction responses are shown
- Strike analysis responses are displayed in full
- API call details and token usage are logged

## 📚 Research Context

This pipeline was developed for analyzing historical labor movements in early 20th century Hungary using the Népszava newspaper archive. The "TŐKE ÉS MUNKA" column was a regular feature that reported on strikes, labor disputes, and working conditions.

### Data Quality Notes

- OCR quality varies by newspaper condition and age
- Some dates may be extracted from filenames when headers are unclear
- Manual verification of key results is recommended for research use
- The AI extraction is designed to be conservative - unclear information is marked as such

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is open source. Please check with the repository owner for specific licensing terms.

## 🔗 Related Projects

- [Model Context Protocol](https://github.com/modelcontextprotocol) - For advanced AI-powered data processing
- [OpenAI Python SDK](https://github.com/openai/openai-python) - For AI API integration

## 📞 Support

For questions or issues:
1. Check the troubleshooting section above
2. Review the detailed setup in `README_strike_cleaner.md`
3. Open an issue on GitHub with detailed error information and context