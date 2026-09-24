import os
import re
import sys
import pandas as pd


def main():
  # 1. 실행 파일(또는 스크립트)이 위치한 디렉터리 경로 설정
  if getattr(sys, "frozen", False):
    # PyInstaller 등으로 패키징된 실행 파일인 경우
    base_dir = os.path.dirname(os.path.abspath(sys.executable))
  else:
    # 일반 파이썬 스크립트인 경우
    base_dir = os.path.dirname(os.path.abspath(__file__))

  # 2. 엑셀 파일명 지정 (필요에 따라 파일명 변경 가능)
  excel_filename = "키움 REST API 문서.xlsx"
  excel_path = os.path.join(base_dir, excel_filename)

  if not os.path.exists(excel_path):
    print(f"오류: 엑셀 파일을 찾을 수 없습니다 -> {excel_path}")
    return

  # 3. 저장할 '/tr_docs' 디렉터리 생성
  output_dir = os.path.join(base_dir, "tr_docs")
  os.makedirs(output_dir, exist_ok=True)

  try:
    # 4. 엑셀 파일 로드
    excel_file = pd.ExcelFile(excel_path)
    print(f"총 {len(excel_file.sheet_names)}개의 시트를 처리합니다...\n")

    for sheet_name in excel_file.sheet_names:
      # 시트 데이터 읽기
      df = pd.read_excel(excel_file, sheet_name=sheet_name)

      # 5. 시트 제목에 괄호가 있는 경우 괄호 안의 문자열 추출
      match = re.search(r"\((.*?)\)", sheet_name)
      if match:
        file_name = match.group(1)
      else:
        file_name = sheet_name

      # 파일명으로 사용할 수 없는 특수문자 제거 (안전 장치)
      file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
      md_filename = f"{file_name}.md"
      md_path = os.path.join(output_dir, md_filename)

      # 6. 데이터프레임을 마크다운 형식으로 변환
      try:
        md_table = df.to_markdown(index=False)
      except Exception:
        # tabulate 미설치 등으로 변환 실패 시 텍스트 형태로 대체
        md_table = "```text\n" + df.to_string(index=False) + "\n```"

      # 7. 마크다운 파일로 저장 (UTF-8 인코딩)
      with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 시트 제목: {sheet_name}\n\n")
        f.write(md_table if md_table else "데이터가 없습니다.")

      print(f"저장 완료: {sheet_name} -> tr_docs/{md_filename}")

    print("\n모든 시트의 마크다운 변환 작업이 성공적으로 완료되었습니다!")

  except Exception as e:
    print(f"작업 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
  main()