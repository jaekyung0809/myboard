import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv
from datetime import datetime
import json
import csv
from io import StringIO
from flask import make_response

# 로컬 환경에서는 .env를 읽고, Azure에서는 패스.
if os.path.exists('.env'):
    load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# 데이터베이스 연결 함수
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'), 
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        sslmode='require', #Azure를 위해 반드시 추가
        options = '-c timezone=Asia/Seoul'
    )
    print('get_db_connection', conn)
    conn.autocommit = True
    return conn

@app.route('/')
def index():
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    print('get_db_connection', conn)
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. SELECT
    cursor.execute("SELECT id, title, author, created_at, view_count, like_count FROM board.posts ORDER BY created_at DESC")
    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    # 3. index.html 파일에 변수로 넘겨주기
    return render_template('index.html', posts = posts)

@app.route('/create/', methods=['GET'] )
def create_form():
    return render_template('create.html')

@app.route('/create/',methods=['POST']  )
def create_post():
    #1. 폼에 있는 정보들을 get
    title = request.form.get('title')
    author = request.form.get('author')
    content = request.form.get('content')

    if not title or not author or not content:
        flash('모든 필드를 똑바로 채워주세요!!!!')
        return redirect(url_for('create_form'))
    
    # 1. 데이터 베이스에 접속
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    # 2. INSERT
    cursor.execute("INSERT INTO board.posts (title, content, author) VALUES (%s, %s, %s) RETURNING id", (title, content, author))
    post_id = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    flash('게시글이 성공적으로 등록되었음')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('UPDATE board.posts SET view_count = view_count + 1 WHERE id = %s', (post_id,))
    
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    
    if post is None:
        cursor.close()
        conn.close()
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    cursor.execute('SELECT * FROM board.comments WHERE post_id = %s ORDER BY created_at', (post_id,))
    comments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    user_ip = request.remote_addr
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    liked = cursor.fetchone()[0] > 0
    cursor.close()
    conn.close()
    
    return render_template('view.html', post=post, comments=comments, liked=liked)

@app.route('/edit/<int:post_id>', methods=['GET'])
def edit_form(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute('SELECT * FROM board.posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if post is None:
        flash('게시글을 찾을 수 없습니다.')
        return redirect(url_for('index'))
    
    return render_template('edit.html', post=post)

@app.route('/edit/<int:post_id>', methods=['POST'])
def edit_post(post_id):
    title = request.form.get('title')
    content = request.form.get('content')
    
    if not title or not content:
        flash('제목과 내용을 모두 입력해주세요.')
        return redirect(url_for('edit_form', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE board.posts SET title = %s, content = %s, updated_at = %s WHERE id = %s',
        (title, content, datetime.now(), post_id)
    )
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 수정되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM board.posts WHERE id = %s', (post_id,))
    cursor.close()
    conn.close()
    
    flash('게시글이 성공적으로 삭제되었습니다.')
    return redirect(url_for('index'))

@app.route('/post/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    author = request.form.get('author')
    content = request.form.get('content')
    
    if not author or not content:
        flash('작성자와 내용을 모두 입력해주세요.')
        return redirect(url_for('view_post', post_id=post_id))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO board.comments (post_id, author, content) VALUES (%s, %s, %s)',
        (post_id, author, content)
    )
    cursor.close()
    conn.close()
    
    flash('댓글이 등록되었습니다.')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/like/<int:post_id>', methods=['POST'])
def like_post(post_id):
    user_ip = request.remote_addr
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
    already_liked = cursor.fetchone()[0] > 0
    
    if already_liked:
        cursor.execute('DELETE FROM board.likes WHERE post_id = %s AND user_ip = %s', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count - 1 WHERE id = %s', (post_id,))
        message = '좋아요가 취소되었습니다.'
    else:
        cursor.execute('INSERT INTO board.likes (post_id, user_ip) VALUES (%s, %s)', (post_id, user_ip))
        cursor.execute('UPDATE board.posts SET like_count = like_count + 1 WHERE id = %s', (post_id,))
        message = '좋아요가 등록되었습니다.'
    
    cursor.close()
    conn.close()   
    flash(message)
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/fms/result')
def fms_result():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    results = []
    summary = {'total': 0, 'pass': 0, 'fail': 0}
    
    # 시각화용 데이터
    weights_all = []
    weights_by_breed = {}
    scatter_data = []

    try:
        cursor.execute("SELECT * FROM fms.total_result")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        summary['total'] = len(results)
        
        for row in results:
            # ---------------------------------------------------------
            # [수정된 부분] 한글 '부적합' 뿐만 아니라 영어 'Fail'도 잡아냅니다!
            # ---------------------------------------------------------
            # 1. '부적합여부' 컬럼의 값을 가져와서 문자로 변환(str)하고 공백제거(strip)
            status = str(row.get('부적합여부', '')).strip()
            
            # 2. '부적합' 이거나 'Fail' (대소문자 상관없이) 이면 Fail 카운트
            if status == '부적합' or status.lower() == 'fail':
                summary['fail'] += 1
            else:
                summary['pass'] += 1
            # ---------------------------------------------------------
            
            # 데이터 추출
            breed = row.get('품종', 'Unknown')
            weight = row.get('종란무게', 0)
            doc_id = row.get('육계번호', 0)

            # 무게 데이터 숫자 변환
            weight_val = 0
            try:
                weight_val = float(str(weight).replace('g', '').replace(',', '').strip())
            except:
                weight_val = 0

            if weight_val > 0:
                weights_all.append(weight_val)
                
                if breed not in weights_by_breed:
                    weights_by_breed[breed] = []
                weights_by_breed[breed].append(weight_val)

                scatter_data.append({
                    'id': doc_id,
                    'weight': weight_val,
                    'breed': breed
                })
                
    except Exception as e:
        print(f"오류 발생: {e}")
        
    finally:
        cursor.close()
        conn.close()

    return render_template('fms_result.html', 
                           results=results, 
                           summary=summary, 
                           weights_all=weights_all,
                           weights_by_breed=weights_by_breed,
                           scatter_data=scatter_data)

@app.route('/fms/export')
def export_fms():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    try:
        cursor.execute("SELECT * FROM fms.total_result")
        rows = cursor.fetchall()
        
        # 1. 메모리에 파일 생성 (가상 파일)
        si = StringIO()
        cw = csv.writer(si)
        
        if rows:
            # 2. 헤더(컬럼명) 쓰기
            cw.writerow(rows[0].keys())
            # 3. 데이터 쓰기
            for row in rows:
                cw.writerow(row.values())
                
        # 4. 파일 다운로드 응답 만들기
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=fms_result.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    except Exception as e:
        print(f"다운로드 중 오류: {e}")
        return "다운로드 중 오류가 발생했습니다."
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)

