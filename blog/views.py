from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.generic import ListView
from .models import Post, Comment
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from .forms import EmailPostForm, CommentForm, SearchForm
from django.core.mail import send_mail
from django.contrib.postgres.search import TrigramSimilarity
from taggit.models import Tag
from django.db.models import Count


def post_list(request, tag_slug=None):
    object_list = Post.published.all()
    tag = None
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        object_list = object_list.filter(tags__in=[tag])
    paginator = Paginator(object_list, 3)
    # 3 posts in each page
    page = request.GET.get('page')
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer deliver the first page
        posts = paginator.page(1)
    except EmptyPage:
        # If page is out of range deliver last page of results
        posts = paginator.page(paginator.num_pages)
    return render(request,
                  'blog/post/list.html',
                  {'page': page,
                   'posts': posts, 'tag': tag})


def post_detail(request, year, month, day, post):
    post = get_object_or_404(Post, slug=post, status='published',
                             publish__year=year, publish__month=month,
                             publish__day=day)
    comments = post.comments.filter(active=True)
    new_comment = None
    if request.method == 'POST':
        # Пользователь отправил комментарий
        comment_form = CommentForm(data=request.POST)
        if comment_form.is_valid():
            # создаем комментарий но не сохраняем в базе
            new_comment = comment_form.save(commit=False)
            # Привязываем комментарий к текущей статье
            new_comment.post = post
            new_comment.save()
    else:
        comment_form = CommentForm()

    post_tags_ids = post.tags.values_list('id', flat=True)
    similar_posts = Post.published.filter(tags__in=post_tags_ids).exclude(id=post.id)
    similar_posts = similar_posts.annotate(same_tags=Count('tags')).order_by('-same_tags', '-publish')[:4]

    return render(request, 'blog/post/detail.html',
                  context={'post': post, 'comments': comments,
                           'new_comment': new_comment, 'comment_form': comment_form, 'similar_posts': similar_posts})


class PostListView(ListView):
    queryset = Post.published.all()
    context_object_name = 'posts'
    paginate_by = 3
    template_name = 'blog/post/list.html'


def post_share(request, post_id):
    # Получить статью по id
    post = get_object_or_404(Post, id=post_id, status='published')
    sent = False

    if request.method == 'POST':
        # форма была отправлена на сохранение
        form = EmailPostForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # ... Отправка эл почты
            post_url = request.build_absolute_uri(post.get_absolute_url())
            subject = '{}({}) recommends you reading "{}"'.format(cd['name'],
                                                                  cd['email'], post.title)
            message = 'Read "{}" at {}\n\n{}\'s comments {}'.format(post.title,
                                                                    post_url, cd['name'], cd['comments'])
            send_mail(subject, message, 'admin@myblog.com', [cd['to']])
            sent = True
    else:
        form = EmailPostForm()
    return render(request, 'blog/post/share.html',
                  context={'post': post, 'form': form, 'sent': sent})


def post_search(request):
    form = SearchForm()
    query = None
    results = []
    if 'query' in request.GET:
        form = SearchForm(request.GET)
    if form.is_valid():
        query = form.cleaned_data['query']
        search_vector = SearchVector('title', weight='A') + SearchVector('body', weight='B')
        search_query = SearchQuery(query)
        results = Post.objects.annotate(similarity=TrigramSimilarity('title', query)
                                        ).filter(similarity__gt=0.3).order_by('-similarity')
    return render(request, 'blog/post/search.html', context={'form': form,
                                                             'query': query, 'results': results})